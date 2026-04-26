"""
enrich_rallies.py — Fleet-powered rally research enrichment.

Uses Willow's free LLM fleet to look up public facts about scooter rallies
and backfill meta.json with real descriptions, club info, locations, etc.

Usage:
    python enrich_rallies.py                  # enrich all unenriched rallies
    python enrich_rallies.py --limit 20       # do 20 at a time
    python enrich_rallies.py --year 2003      # only 2003 rallies
    python enrich_rallies.py --dry-run        # show what would be enriched
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path

# Wire up fleet — need both core dir and parent for relative imports
WILLOW_ROOT = "/mnt/c/Users/Sean/Documents/GitHub/Willow"
sys.path.insert(0, WILLOW_ROOT)
sys.path.insert(0, os.path.join(WILLOW_ROOT, "core"))
import llm_router
llm_router.load_keys_from_json()

DATA_DIR = Path("/mnt/c/Users/Sean/Documents/GitHub/safe-app-nasa-archive/data/rallies")
INDEX_PATH = Path("/mnt/c/Users/Sean/Documents/GitHub/safe-app-nasa-archive/web/data/rallies.json")

PROMPT_TEMPLATE = """You are a research librarian specializing in motor scooter culture and rally history in North America and worldwide.

I need factual information about this scooter rally:

Rally Name: {name}
Year: {year}
Month: {month}
Scoot.net URL: {url}

Please provide what you know as JSON with these fields (use null for anything you don't know — do NOT make things up):

{{
  "description": "1-3 sentence description of what this rally was",
  "hosting_club": "name of the scooter club that organized it, or null",
  "city": "city where it was held",
  "state_province": "state or province",
  "country": "country (default US if clearly American)",
  "recurring": true/false if this was an annual/recurring event,
  "first_year": year the rally series started or null,
  "notable_facts": ["any notable facts, up to 3"],
  "related_clubs": ["other clubs involved or attending"],
  "source_confidence": "high/medium/low — how confident you are in this info"
}}

IMPORTANT: Only state facts you're confident about. "null" is better than a guess. These are real community events and accuracy matters. Respond with ONLY the JSON object, no other text."""


def load_index():
    with open(INDEX_PATH) as f:
        data = json.load(f)
    return [
        {
            "name": r.get("n", ""),
            "year": r.get("y", None),
            "slug": r.get("s", ""),
            "description": r.get("d", ""),
        }
        for r in data
    ]


def slug_to_dir(slug):
    return slug.replace("/", "-")


def needs_enrichment(rally):
    """Check if this rally needs enrichment."""
    dir_slug = slug_to_dir(rally["slug"])
    meta_path = DATA_DIR / dir_slug / "meta.json"
    if not meta_path.exists():
        return True
    meta = json.load(open(meta_path))
    # Already enriched if it has a real description or enrichment data
    if meta.get("enriched"):
        return False
    if meta.get("hosting_club") or meta.get("city"):
        return False
    return True


def enrich_one(rally):
    """Ask the fleet about one rally. Returns enrichment dict or None."""
    slug = rally["slug"]
    month_num = 0
    m = __import__("re").match(r"\d{4}/(\d{2})/", slug)
    if m:
        month_num = int(m.group(1))

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    month_str = month_names[month_num] if month_num else "Unknown"
    url = f"http://scoot.net/gallery/{slug}/" if "/" in slug else ""

    prompt = PROMPT_TEMPLATE.format(
        name=rally["name"],
        year=rally["year"] or "Unknown",
        month=month_str,
        url=url or "N/A",
    )

    try:
        resp = llm_router.ask(prompt, preferred_tier="free", task_type="text_summarization")
        if not resp or not resp.content:
            return None

        # Parse JSON from response — handle markdown code fences
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        data["enriched"] = True
        data["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["enriched_provider"] = resp.provider
        return data

    except json.JSONDecodeError as e:
        print(f"  JSON parse error for {rally['name']}: {e}")
        return None
    except Exception as e:
        print(f"  Fleet error for {rally['name']}: {e}")
        return None


def update_meta(rally, enrichment):
    """Merge enrichment data into meta.json."""
    dir_slug = slug_to_dir(rally["slug"])
    meta_path = DATA_DIR / dir_slug / "meta.json"

    if meta_path.exists():
        meta = json.load(open(meta_path))
    else:
        # Create minimal meta if dir exists but no meta.json
        meta_dir = DATA_DIR / dir_slug
        if not meta_dir.exists():
            meta_dir.mkdir(parents=True)
        meta = {
            "slug": rally["slug"],
            "title": rally["name"],
            "year": rally["year"],
        }

    # Merge enrichment — don't overwrite existing real data with nulls
    for key, val in enrichment.items():
        if val is not None:
            meta[key] = val

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return meta_path


def update_index(rallies_enriched):
    """Update rallies.json descriptions from enrichment data."""
    with open(INDEX_PATH) as f:
        index = json.load(f)

    lookup = {}
    for enrichment, rally in rallies_enriched:
        if enrichment and enrichment.get("description"):
            lookup[rally["slug"]] = enrichment["description"]

    changed = 0
    for entry in index:
        slug = entry.get("s", "")
        if slug in lookup:
            old_desc = entry.get("d", "")
            # Preserve photo count from old description
            photo_note = ""
            import re
            m = re.search(r"\d+ photos?\.", old_desc)
            if m:
                photo_note = " " + m.group(0)
            entry["d"] = lookup[slug] + photo_note
            changed += 1

    if changed > 0:
        with open(INDEX_PATH, "w") as f:
            json.dump(index, f, separators=(",", ":"))
        print(f"Updated {changed} descriptions in rallies.json")


def main():
    parser = argparse.ArgumentParser(description="Enrich rally data via fleet")
    parser.add_argument("--limit", type=int, default=0, help="Max rallies to process")
    parser.add_argument("--year", type=int, default=0, help="Only this year")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    args = parser.parse_args()

    rallies = load_index()
    print(f"Loaded {len(rallies)} rallies from index")

    # Filter
    if args.year:
        rallies = [r for r in rallies if r["year"] == args.year]
        print(f"Filtered to {len(rallies)} rallies in {args.year}")

    to_enrich = [r for r in rallies if needs_enrichment(r)]
    print(f"{len(to_enrich)} need enrichment")

    if args.limit:
        to_enrich = to_enrich[:args.limit]
        print(f"Limited to {args.limit}")

    if args.dry_run:
        for r in to_enrich:
            print(f"  Would enrich: {r['name']} ({r['year']})")
        return

    results = []
    success = 0
    fail = 0
    queue = list(to_enrich)
    attempt = 0
    backoff = args.delay
    max_backoff = 60.0  # cap backoff at 60s
    consecutive_fails = 0

    while queue:
        attempt += 1
        rally = queue.pop(0)
        remaining = len(queue)
        print(f"[pass {attempt} | {remaining} left | {success} done] {rally['name']} ({rally['year']})...", end=" ", flush=True)

        enrichment = enrich_one(rally)
        if enrichment:
            path = update_meta(rally, enrichment)
            conf = enrichment.get("source_confidence", "?")
            club = enrichment.get("hosting_club", "?")
            city = enrichment.get("city", "?")
            print(f"OK — {club}, {city} [{conf}]")
            results.append((enrichment, rally))
            success += 1
            consecutive_fails = 0
            backoff = args.delay  # reset backoff on success
        else:
            print(f"RETRY (back of queue)")
            queue.append(rally)  # back of the line
            consecutive_fails += 1

            # Exponential backoff when fleet is struggling
            if consecutive_fails >= 5:
                backoff = min(backoff * 1.5, max_backoff)
                print(f"  Fleet struggling — {consecutive_fails} consecutive fails, backing off to {backoff:.0f}s")

            # Periodic index update so progress isn't lost
            if success > 0 and success % 25 == 0:
                update_index(results)

        time.sleep(backoff)

    print(f"\nDone: {success} enriched, {fail} skipped")

    # Final index update
    if success > 0:
        update_index(results)


if __name__ == "__main__":
    main()
