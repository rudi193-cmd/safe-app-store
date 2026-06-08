#!/usr/bin/env python3
"""
bbs_scraper.py -- scooterbbs.com Wayback Machine archive scraper
Mirrors gallery_scraper.py pattern for NASA archive integration.

Phase 1: CDX index -- map all captures, find thread URLs
Phase 2: Content scrape -- extract posts, authors, dates from archived pages
Phase 3: Output JSON for integration with index.json

Usage:
    python bbs_scraper.py --phase index     # Map all captures (fast)
    python bbs_scraper.py --phase scrape    # Pull thread content (slow)
    python bbs_scraper.py --phase all       # Both
"""

import argparse
import json
import re
import time
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# --- Config ---
BBS_DOMAIN = "scooterbbs.com"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CDX_INDEX_FILE = OUTPUT_DIR / "bbs_cdx_index.json"
THREADS_FILE = OUTPUT_DIR / "bbs_threads.json"
POSTS_FILE = OUTPUT_DIR / "bbs_posts.json"
SUMMARY_FILE = OUTPUT_DIR / "bbs_summary.json"

CHECKPOINT_FILE = OUTPUT_DIR / "bbs_checkpoint.json"

HEADERS = {
    "User-Agent": "NASA-Archive-Bot/1.0 (scooter rally preservation; contact via github)",
}
REQUEST_DELAY = 1.5  # seconds between requests (be polite)


# --- CDX Index Phase ---

def fetch_cdx_index(limit=None):
    """Query Wayback CDX API for all scooterbbs.com captures."""
    print(f"\nQuerying CDX API for {BBS_DOMAIN}...")

    params = {
        "url": f"{BBS_DOMAIN}/*",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "collapse": "urlkey",  # deduplicate by URL
    }
    if limit:
        params["limit"] = limit

    try:
        r = requests.get(WAYBACK_CDX, params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [ERROR] CDX fetch failed: {e}")
        return []

    if not data or len(data) < 2:
        print("  No captures found.")
        return []

    # First row is header
    headers = data[0]
    rows = data[1:]

    captures = []
    for row in rows:
        entry = dict(zip(headers, row))
        captures.append(entry)

    print(f"  Found {len(captures)} unique URLs")
    CDX_INDEX_FILE.write_text(json.dumps(captures, indent=2), encoding="utf-8")
    print(f"  -> Saved {CDX_INDEX_FILE}")
    return captures


def classify_urls(captures):
    """Separate thread URLs from navigation/index pages."""
    threads = []
    index_pages = []

    # BBS thread patterns (common phpBB, vBulletin, UBB patterns)
    thread_patterns = [
        r"viewtopic",
        r"showthread",
        r"topic=\d+",
        r"thread=\d+",
        r"t=\d+",
        r"msg\d+",
        r"post\d+",
        r"/forums?/.*\d+",
    ]

    for cap in captures:
        url = cap["original"]
        is_thread = any(re.search(p, url, re.IGNORECASE) for p in thread_patterns)

        # Filter out images, css, js
        mime = cap.get("mimetype", "")
        if not mime.startswith("text/"):
            continue

        if is_thread:
            threads.append(cap)
        else:
            index_pages.append(cap)

    print(f"\n  Thread URLs: {len(threads)}")
    print(f"  Index/nav pages: {len(index_pages)}")

    THREADS_FILE.write_text(json.dumps({
        "threads": threads,
        "index_pages": index_pages[:50]  # sample
    }, indent=2), encoding="utf-8")
    print(f"  -> Saved {THREADS_FILE}")
    return threads, index_pages


# --- Content Scrape Phase ---

def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"scraped": [], "failed": []}


def save_checkpoint(cp):
    CHECKPOINT_FILE.write_text(json.dumps(cp), encoding="utf-8")


def scrape_wayback_thread(timestamp, original_url):
    """Fetch a thread from Wayback Machine and extract posts."""
    wayback_url = f"{WAYBACK_BASE}/{timestamp}/{original_url}"
    try:
        r = requests.get(wayback_url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None, wayback_url

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove Wayback toolbar
        for el in soup.find_all("div", id=re.compile(r"wm-ipp|donato")):
            el.decompose()

        posts = []

        # Try common BBS post selectors (phpBB, UBB, vBulletin)
        post_containers = (
            soup.find_all("div", class_=re.compile(r"post|message|entry")) or
            soup.find_all("table", class_=re.compile(r"post|message")) or
            soup.find_all("td", class_=re.compile(r"post|message|post-content"))
        )

        for pc in post_containers[:50]:  # cap at 50 posts per thread
            text = pc.get_text(separator=" ", strip=True)
            if len(text) < 20:  # skip nav fragments
                continue
            posts.append({
                "text": text[:2000],
                "length": len(text),
            })

        # Get thread title
        title = ""
        h1 = soup.find("h1") or soup.find("title")
        if h1:
            title = h1.get_text(strip=True)[:200]

        return {
            "url": original_url,
            "wayback_url": wayback_url,
            "timestamp": timestamp,
            "date": f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}",
            "title": title,
            "post_count": len(posts),
            "posts": posts,
        }, wayback_url

    except Exception as e:
        return None, f"{wayback_url} -- {e}"


def scrape_threads(threads, limit=None):
    """Scrape thread content from Wayback snapshots."""
    cp = load_checkpoint()
    already_done = set(cp["scraped"])
    results = []
    posts_file = OUTPUT_DIR / "bbs_posts_raw.jsonl"

    targets = [t for t in threads if t["original"] not in already_done]
    if limit:
        targets = targets[:limit]

    print(f"\nScraping {len(targets)} threads ({len(already_done)} already done)...")

    for i, thread in enumerate(targets, 1):
        url = thread["original"]
        ts = thread["timestamp"]

        print(f"  [{i}/{len(targets)}] {url[:60]}...", end=" ", flush=True)
        result, info = scrape_wayback_thread(ts, url)

        if result:
            post_count = result["post_count"]
            title_short = result["title"][:40]
            print(f"[{post_count} posts] {title_short}")
            results.append(result)
            with open(posts_file, "a", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
                f.write("\n")
            cp["scraped"].append(url)
        else:
            print(f"[FAILED] {info[:60]}")
            cp["failed"].append(url)

        if i % 25 == 0:
            save_checkpoint(cp)
            print(f"  [checkpoint saved -- {i}/{len(targets)}]")

        time.sleep(REQUEST_DELAY)

    save_checkpoint(cp)
    failed_count = len(cp["failed"])
    print(f"\nDone: {len(results)} threads scraped, {failed_count} failed")
    return results


# --- Summary ---

def write_summary(captures, threads, index_pages):
    summary = {
        "domain": BBS_DOMAIN,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "total_captures": len(captures),
        "thread_urls": len(threads),
        "index_pages": len(index_pages),
        "output_files": {
            "cdx_index": str(CDX_INDEX_FILE),
            "threads": str(THREADS_FILE),
            "posts_raw": str(OUTPUT_DIR / "bbs_posts_raw.jsonl"),
            "summary": str(SUMMARY_FILE),
        }
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n-> Saved {SUMMARY_FILE}")
    return summary


# --- Main ---

def main():
    p = argparse.ArgumentParser(description="scooterbbs.com Wayback scraper")
    p.add_argument("--phase", choices=["index", "scrape", "all"], default="index",
                   help="index=CDX map only, scrape=pull content, all=both")
    p.add_argument("--limit", type=int, default=None, help="Max threads to scrape")
    p.add_argument("--cdx-limit", type=int, default=None, help="Max CDX captures to fetch")
    args = p.parse_args()

    print("=" * 55)
    print("  scooterbbs.com -- Wayback Machine Scraper")
    print("=" * 55)

    captures = []
    threads = []
    index_pages = []

    if args.phase in ("index", "all"):
        captures = fetch_cdx_index(limit=args.cdx_limit)
        if captures:
            threads, index_pages = classify_urls(captures)
        write_summary(captures, threads, index_pages)

    if args.phase in ("scrape", "all"):
        if not threads:
            if THREADS_FILE.exists():
                data = json.loads(THREADS_FILE.read_text())
                threads = data.get("threads", [])
                index_pages = data.get("index_pages", [])
            else:
                print("Run --phase index first")
                return
        scrape_threads(threads, limit=args.limit)

    print("\nNext: python bbs_scraper.py --phase scrape --limit 100")


if __name__ == "__main__":
    main()
