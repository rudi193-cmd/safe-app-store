import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import piexif
import requests
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = "http://scoot.net"
GALLERY_FULL = Path(__file__).parent.parent / "scraper" / "output" / "gallery_full.json"
DATA_DIR = Path(__file__).parent.parent / "data" / "rallies"
RESOLVED_FILE = Path(__file__).parent / "resolved_urls.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NASA-Archive-Bot/1.0; archival research)"}
WORKERS = 10
DELAY = 0.3


def get_r2_client():
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def resolve_one(photo):
    """Fetch pic.html, extract small_ image URL and attempt full-size URL."""
    time.sleep(DELAY)
    try:
        r = requests.get(photo["pic_url"], headers=HEADERS, timeout=20)
        r.raise_for_status()
        m = re.search(r'<IMG SRC="(/gallery/[^"]+)"', r.text, re.IGNORECASE)
        if not m:
            return photo["pic_id"], None, None
        small_url = BASE_URL + m.group(1)
        full_url = None
        candidate = small_url.replace("/small_", "/")
        if candidate != small_url:
            try:
                head = requests.head(candidate, headers=HEADERS, timeout=10)
                if head.status_code == 200:
                    full_url = candidate
            except Exception:
                pass
        return photo["pic_id"], small_url, full_url
    except Exception as e:
        print(f"    [ERROR] pic {photo['pic_id']}: {e}")
        return photo["pic_id"], None, None


def phase1_resolve(rallies):
    """Resolve all image URLs using thread pool. Saves resolved_urls.json with checkpoints."""
    all_photos = [p for rally in rallies for p in rally.get("photos", [])]

    # Resume from checkpoint if exists
    RESOLVED_FILE.parent.mkdir(parents=True, exist_ok=True)
    resolved = {}
    if RESOLVED_FILE.exists():
        with open(RESOLVED_FILE) as f:
            resolved = json.load(f)
        print(f"  Resuming from checkpoint: {len(resolved):,} already resolved")

    already = set(resolved.keys())
    remaining = [p for p in all_photos if p["pic_id"] not in already]
    print(f"Phase 1: Resolving {len(remaining):,} image URLs ({len(already):,} cached, {WORKERS} workers)...")

    if not remaining:
        found = sum(1 for v in resolved.values() if v["small_url"])
        print(f"  Already complete. {found:,}/{len(all_photos):,} URLs resolved.")
        return resolved

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(resolve_one, p): p for p in remaining}
        for future in as_completed(futures):
            pic_id, small_url, full_url = future.result()
            resolved[pic_id] = {"small_url": small_url, "full_url": full_url}
            done += 1
            if done % 500 == 0:
                print(f"  {done:,}/{len(remaining):,} resolved (total {len(resolved):,})...")
                with open(RESOLVED_FILE, "w") as f:
                    json.dump(resolved, f)
    with open(RESOLVED_FILE, "w") as f:
        json.dump(resolved, f, indent=2)
    found = sum(1 for v in resolved.values() if v["small_url"])
    print(f"  Done. {found:,}/{len(all_photos):,} URLs resolved.")
    return resolved


def extract_exif(img_bytes):
    """
    Extract EXIF from image bytes.
    Stored as-is, never used as canonical date truth.
    Camera clocks in the 2000s-era were notoriously unreliable.
    """
    try:
        exif_raw = piexif.load(img_bytes)
        out = {}
        ifd = exif_raw.get("Exif", {})
        zeroth = exif_raw.get("0th", {})
        if piexif.ExifIFD.DateTimeOriginal in ifd:
            out["DateTimeOriginal"] = ifd[piexif.ExifIFD.DateTimeOriginal].decode("utf-8", errors="replace")
        if piexif.ImageIFD.Make in zeroth:
            out["Make"] = zeroth[piexif.ImageIFD.Make].decode("utf-8", errors="replace").strip()
        if piexif.ImageIFD.Model in zeroth:
            out["Model"] = zeroth[piexif.ImageIFD.Model].decode("utf-8", errors="replace").strip()
        out["_warning"] = "Camera clock accuracy not guaranteed. Use date_canonical for trusted dates."
        return out if len(out) > 1 else None
    except Exception:
        return None


def process_one(args):
    """Download image, extract EXIF, upload thumb + full to R2."""
    photo, resolved, r2, bucket, public_url = args
    pic_id = photo["pic_id"]
    urls = resolved.get(pic_id, {})
    small_url = urls.get("small_url")
    full_url = urls.get("full_url")

    if not small_url:
        return {**photo, "r2_thumb": None, "r2_full": None, "date_exif": None, "exif_meta": None}

    time.sleep(DELAY)
    try:
        resp = requests.get(small_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        img_bytes = resp.content
    except Exception as e:
        print(f"    [ERROR] download {pic_id}: {e}")
        return {**photo, "r2_thumb": None, "r2_full": None, "date_exif": None, "exif_meta": None}

    exif = extract_exif(img_bytes)
    date_exif = exif.get("DateTimeOriginal") if exif else None

    date_part = (photo.get("date_rally") or "unknown").replace("-", "")
    photographer = photo.get("photographer") or "unknown"
    thumb_key = f"gallery/{date_part}-{photographer}/{pic_id}/thumb.jpg"
    full_key = f"gallery/{date_part}-{photographer}/{pic_id}/full.jpg"

    try:
        r2.put_object(Bucket=bucket, Key=thumb_key, Body=img_bytes, ContentType="image/jpeg")
    except Exception as e:
        print(f"    [ERROR] R2 upload {pic_id}: {e}")
        return {**photo, "r2_thumb": None, "r2_full": None, "date_exif": date_exif, "exif_meta": exif}

    r2_full_url = None
    if full_url:
        try:
            time.sleep(DELAY)
            full_resp = requests.get(full_url, headers=HEADERS, timeout=30)
            if full_resp.status_code == 200:
                r2.put_object(Bucket=bucket, Key=full_key, Body=full_resp.content, ContentType="image/jpeg")
                r2_full_url = f"{public_url}/{full_key}"
        except Exception:
            pass

    return {
        **photo,
        "r2_thumb": f"{public_url}/{thumb_key}",
        "r2_full": r2_full_url,
        "date_exif": date_exif,
        "exif_meta": exif,
    }


def phase2_download(rallies, resolved):
    """Download all images, upload to R2, write data/rallies/{slug}/."""
    r2 = get_r2_client()
    bucket = os.environ["R2_BUCKET"]
    public_url = os.environ["R2_PUBLIC_URL"].rstrip("/")
    print(f"Phase 2: Downloading and uploading ({WORKERS} workers)...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Track completed rallies for resume
    progress_file = Path(__file__).parent / "phase2_progress.json"
    completed_slugs = set()
    if progress_file.exists():
        with open(progress_file) as f:
            completed_slugs = set(json.load(f))
        print(f"  Resuming: {len(completed_slugs):,} rallies already done")

    total_rallies = sum(1 for r in rallies if r.get("photos"))
    done_count = len(completed_slugs)

    for rally in rallies:
        slug = rally["slug"].replace("/", "-")
        photos = rally.get("photos", [])
        if not photos:
            continue
        if slug in completed_slugs:
            continue
        title = rally.get("title") or slug
        done_count += 1
        print(f"  [{done_count}/{total_rallies}] {title} ({len(photos)} photos)")
        args_list = [(p, resolved, r2, bucket, public_url) for p in photos]
        updated = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for result in pool.map(process_one, args_list):
                updated.append(result)

        out_dir = DATA_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "photos.json", "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)

        meta = {k: v for k, v in rally.items() if k != "photos"}
        meta["photo_count"] = len(updated)
        meta["stories"] = []
        with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # Checkpoint after each rally
        completed_slugs.add(slug)
        with open(progress_file, "w") as f:
            json.dump(sorted(completed_slugs), f)

    print("  Phase 2 complete.")


def main():
    parser = argparse.ArgumentParser(description="NASA Archive Downloader")
    parser.add_argument("--phase", type=int, choices=[1, 2], help="Run only phase 1 or 2")
    args = parser.parse_args()

    with open(GALLERY_FULL) as f:
        rallies = json.load(f)
    print(f"Loaded {len(rallies):,} rallies")

    if args.phase in (None, 1):
        resolved = phase1_resolve(rallies)
    else:
        print("Loading resolved_urls.json...")
        with open(RESOLVED_FILE) as f:
            resolved = json.load(f)

    if args.phase in (None, 2):
        phase2_download(rallies, resolved)

    print("Done.")


if __name__ == "__main__":
    main()
