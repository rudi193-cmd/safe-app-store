import json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE_URL = "http://scoot.net"
OUTPUT_DIR = Path(__file__).parent / "output"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NASA-Archive-Bot/1.0; archival research)"}
DELAY = 1.5

def get_page(url):
    time.sleep(DELAY)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"    [ERROR] {url}: {e}")
        return None

def save_json(data, filename):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  -> Saved {path} ({len(data)} entries)")

def extract_date_from_slug(slug):
    """
    Extract year and month from a rally slug.
    Returns dict with year (int|None), month (int|None), date_rally (str).

    Slugs come in two formats:
      chainoffools2002        -> year=2002, month=None, date_rally="2002-??"
      2007/08/campscoot       -> year=2007, month=8,    date_rally="2007-08"

    Month is stored but never treated as authoritative - camera clocks
    were unreliable in this era. date_rally is the human-readable label.
    date_exif (from image file) is preserved separately and never used
    as canonical truth. date_canonical is null until a human sets it.
    """
    year_m = re.search(r"(199[7-9]|200[0-9]|201[0-9]|2020)", slug)
    month_m = re.search(r"/(0[1-9]|1[0-2])/", slug)
    year = int(year_m.group(1)) if year_m else None
    month = int(month_m.group(1)) if month_m else None
    if year and month:
        date_rally = f"{year}-{month:02d}"
    elif year:
        date_rally = f"{year}-??"
    else:
        date_rally = None
    return {"year": year, "month": month, "date_rally": date_rally}

def map_gallery_index():
    print("Mapping gallery index...")
    # Base URL for resolving relative links on the gallery index page
    gallery_base = BASE_URL + "/gallery/"
    soup = get_page(gallery_base + "?year=all")
    if not soup:
        return []

    # Non-rally links to skip
    skip_hrefs = {
        "", "galleryrequest.html", "picture_comments.html", "alltinyindex.html",
    }
    skip_prefixes = ("/", "http", ".", "#", "mailto")
    skip_contains = ("?", "slideshow", "comment", "showlink", "tinyindex", "pic.html")

    rallies, seen = [], set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if h in skip_hrefs:
            continue
        if any(h.startswith(p) for p in skip_prefixes):
            continue
        if any(s in h for s in skip_contains):
            continue
        url = urljoin(gallery_base, h).rstrip("/") + "/"
        if url in seen:
            continue
        seen.add(url)
        slug = h.strip("/")
        dates = extract_date_from_slug(slug)
        rallies.append({
            "url": url,
            "slug": slug,
            "title": a.get_text(strip=True),
            "year": dates["year"],
            "month": dates["month"],
            "date_rally": dates["date_rally"],
        })

    rallies.sort(key=lambda r: (r["year"] or 0, r["slug"]))
    print(f"  Found {len(rallies)} rally galleries")
    return rallies

def map_photographer_dirs(rally_url, soup):
    """Find all photographer subdirectory links on a rally page."""
    dirs = []
    seen = set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        # Relative links that don't start with / or http are photographer dirs
        if h.startswith("/") or h.startswith("http") or h.startswith("."):
            continue
        if h in ("", "alltinyindex.html"):
            continue
        if any(skip in h.lower() for skip in ["slideshow", "comment", "showlink", "tinyindex"]):
            continue
        url = urljoin(rally_url, h)
        if url not in seen:
            seen.add(url)
            dirs.append({"photographer": h.strip("/"), "url": url})
    return dirs


def map_tinyindex(photographer, date_rally):
    """Parse a photographer tinyindex.html, return list of photo records."""
    tinyindex_url = urljoin(photographer["url"], "tinyindex.html")
    soup = get_page(tinyindex_url)
    if not soup:
        return []
    photos = []
    seen = set()
    for area in soup.find_all("area", href=True):
        h = area["href"]
        m = re.search(r"pic=(\d+)", h)
        if not m:
            continue
        pic_id = m.group(1)
        if pic_id in seen:
            continue
        seen.add(pic_id)
        photos.append({
            "pic_id": pic_id,
            "pic_url": urljoin("http://scoot.net", h),
            "photographer": photographer["photographer"],
            # Date provenance - see extract_date_from_slug for rationale
            "date_rally": date_rally,   # from slug, reliable for year/month
            "date_exif": None,          # populated during download, not trusted
            "date_canonical": None,     # human-set, overrides all other fields
            "date_source": "rally_slug", # tracks which field is authoritative
        })
    return photos


def map_rally_photos(rally):
    soup = get_page(rally["url"])
    if not soup:
        return []
    photo_dirs = map_photographer_dirs(rally["url"], soup)
    photos = []
    for d in photo_dirs:
        pics = map_tinyindex(d, rally.get("date_rally"))
        photos.extend(pics)
    return photos

def map_gallery_full(rallies, checkpoint_every=25):
    """
    Map photos for every rally, writing incremental checkpoints so progress
    is never lost if the run is interrupted. Skips rallies already saved.
    """
    total = len(rallies)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = OUTPUT_DIR / "gallery_full.json"
    progress_file = OUTPUT_DIR / "gallery_full_progress.json"

    # Load any existing progress so we can resume
    done_slugs = {}
    if progress_file.exists():
        with open(progress_file, encoding="utf-8") as f:
            done_slugs = {r["slug"]: r for r in json.load(f)}
        print(f"  Resuming — {len(done_slugs)} rallies already mapped")

    result = list(done_slugs.values())
    pending = [r for r in rallies if r["slug"] not in done_slugs]
    already_done = len(done_slugs)
    print(f"Mapping photos across {len(pending)} remaining rallies ({total} total)...")

    for i, rally in enumerate(pending, 1):
        label = rally["title"] or rally["slug"]
        print(f"  [{already_done + i}/{total}] {label}", flush=True)
        photos = map_rally_photos(rally)
        entry = {**rally, "photo_count": len(photos), "photos": photos}
        result.append(entry)
        done_slugs[rally["slug"]] = entry
        print(f"         {len(photos)} photos", flush=True)

        # Write progress checkpoint periodically
        if i % checkpoint_every == 0:
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
            print(f"  [checkpoint saved — {len(result)}/{total}]", flush=True)

    # Write final output and clean up progress file
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    if progress_file.exists():
        progress_file.unlink()
    print(f"  -> Saved {checkpoint_file} ({len(result)} entries)")
    return result

def map_patches():
    print("Mapping patch gallery...")
    soup = get_page(BASE_URL + "/patches/")
    if not soup:
        return []
    patches, seen = [], set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "patch.html" not in h:
            continue
        url = urljoin(BASE_URL + "/patches/", h)
        if url in seen:
            continue
        seen.add(url)
        qs = parse_qs(urlparse(h).query)
        pid = qs.get("p", [None])[0]
        img = a.find("img") or (a.find_parent() and a.find_parent().find("img"))
        img_url = urljoin(BASE_URL + "/patches/", img["src"]) if img and img.get("src") else None
        patches.append({"id": pid, "url": url, "title": a.get_text(strip=True), "img_url": img_url})
    patches.sort(key=lambda p: int(p["id"]) if p["id"] and p["id"].isdigit() else 0)
    print(f"  Found {len(patches)} patches")
    return patches

def map_calendar():
    print("Mapping calendar...")
    for url in [BASE_URL + "/calendar/", BASE_URL + "/events/", BASE_URL + "/rallies/"]:
        soup = get_page(url)
        if soup:
            print(f"  Found at {url}")
            skip = {"home", "gallery", "patches", "forum", "login", "register", "search"}
            events = []
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if len(text) >= 4 and text.lower() not in skip:
                    events.append({"url": urljoin(BASE_URL, a["href"]), "title": text})
            print(f"  Found {len(events)} calendar entries")
            return events
    print("  Calendar not found - skipping")
    return []

def main():
    print("=" * 55)
    print("  NASA - North America Scootering Archive")
    print("  Site Mapper - scoot.net (no downloads)")
    print("=" * 55)
    rallies = map_gallery_index()
    save_json(rallies, "gallery_index.json")
    full = map_gallery_full(rallies)
    save_json(full, "gallery_full.json")
    patches = map_patches()
    save_json(patches, "patches_index.json")
    cal = map_calendar()
    save_json(cal, "calendar.json")
    total_photos = sum(r["photo_count"] for r in full)
    summary = {"rallies": len(rallies), "total_photos_mapped": total_photos, "patches": len(patches), "calendar_entries": len(cal)}
    save_json(summary, "summary.json")
    print()
    print("=" * 55)
    for k, v in summary.items():
        print(f"  {k:.<30} {v:,}")
    print(f"  Output: {OUTPUT_DIR.resolve()}")
    print("  Next: review JSONs, then run downloader.py")

if __name__ == "__main__":
    main()
