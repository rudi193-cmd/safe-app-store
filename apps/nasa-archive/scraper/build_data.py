"""
NASA - North America Scootering Archive
scraper/build_data.py

Reads gallery_full.json (or gallery_full_progress.json if still running)
and generates the data/ directory structure the Astro site reads from.

Run this anytime to refresh the site data:
    python scraper/build_data.py

Output:
    data/index.json              -- master rally list + stats for homepage
    data/rallies/{slug}/meta.json
    data/rallies/{slug}/photos.json
"""

import json
from pathlib import Path

SCRAPER_OUT = Path(__file__).parent / "output"
DATA_DIR = Path(__file__).parent.parent / "data"


def load_gallery():
    full = SCRAPER_OUT / "gallery_full.json"
    progress = SCRAPER_OUT / "gallery_full_progress.json"
    if full.exists():
        print(f"Loading gallery_full.json...")
        return json.loads(full.read_text(encoding="utf-8"))
    elif progress.exists():
        print(f"Loading gallery_full_progress.json (mapper still running)...")
        return json.loads(progress.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError("No gallery data found. Run map_site.py first.")


def load_patches():
    p = SCRAPER_OUT / "patches_index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def load_calendar():
    """Load calendar from scraper output and community submissions, merged."""
    entries = []
    # Scraper output (historical scoot.net calendar)
    scraped = SCRAPER_OUT / "calendar.json"
    if scraped.exists():
        entries += json.loads(scraped.read_text(encoding="utf-8"))
    # Community submissions (committed to data/)
    community = DATA_DIR / "calendar.json"
    if community.exists():
        entries += json.loads(community.read_text(encoding="utf-8"))
    return entries


def build_rally_files(rallies):
    """Write per-rally meta.json and photos.json into data/rallies/{slug}/"""
    rallies_dir = DATA_DIR / "rallies"
    rallies_dir.mkdir(parents=True, exist_ok=True)

    for rally in rallies:
        slug = rally["slug"].replace("/", "-")
        out_dir = rallies_dir / slug
        out_dir.mkdir(exist_ok=True)

        meta = {k: v for k, v in rally.items() if k != "photos"}
        (out_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        photos = rally.get("photos", [])
        (out_dir / "photos.json").write_text(
            json.dumps(photos, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(f"  Wrote {len(rallies)} rally directories")


def build_index(rallies, patches, calendar):
    """Write data/index.json — the master file the homepage and rally list read."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    total_photos = sum(r.get("photo_count", 0) for r in rallies)

    # Slim list for the rallies browse page (no photos array)
    # Read lat/lng from already-geocoded meta.json files (geocode_rallies.py writes these)
    rallies_dir = DATA_DIR / "rallies"
    rallies_list = []
    for r in rallies:
        slug = r["slug"].replace("/", "-")
        lat = lng = None
        meta_path = rallies_dir / slug / "meta.json"
        if meta_path.exists():
            try:
                saved = json.loads(meta_path.read_text(encoding="utf-8"))
                lat = saved.get("lat")
                lng = saved.get("lng")
            except Exception:
                pass
        rallies_list.append({
            "slug": r["slug"],
            "title": r.get("title", ""),
            "year": r.get("year"),
            "month": r.get("month"),
            "date_rally": r.get("date_rally"),
            "photo_count": r.get("photo_count", 0),
            "url": r.get("url", ""),
            "lat": lat,
            "lng": lng,
        })

    index = {
        "rallies": len(rallies),
        "total_photos_mapped": total_photos,
        "patches": len(patches),
        "calendar_entries": len(calendar),
        "rallies_list": rallies_list,
        "calendar_entries_list": calendar,
    }

    (DATA_DIR / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Wrote data/index.json ({len(rallies)} rallies, {total_photos:,} photos)")


def main():
    print("=" * 50)
    print("  NASA Archive — Building site data")
    print("=" * 50)

    rallies = load_gallery()
    patches = load_patches()
    calendar = load_calendar()

    print(f"\nBuilding rally files...")
    build_rally_files(rallies)

    print(f"\nBuilding index...")
    build_index(rallies, patches, calendar)

    print(f"\nDone. Run 'npm run dev' in site/ to preview.")


if __name__ == "__main__":
    main()
