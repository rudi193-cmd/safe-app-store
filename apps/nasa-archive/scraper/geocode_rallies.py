"""
NASA Archive - Rally Geocoder
scraper/geocode_rallies.py

Reads each rally meta.json, determines city/state from slug or title,
geocodes via Nominatim (free, OpenStreetMap), writes lat/lng to meta.json.

Run from repo root:
    python scraper/geocode_rallies.py

Respects Nominatim rate limit (1 req/sec). Skips already-geocoded rallies.
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

RALLIES_DIR = Path(__file__).parent.parent / "data" / "rallies"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "nasa-archive-geocoder/1.0 (sean@die-namic.system)"
RATE_LIMIT_SEC = 1.1

# Manually resolved slugs where slug/title parsing isn't reliable
MANUAL_LOCATIONS = {
    "alpine2000":  ("American Fork", "UT", "USA"),
    "alpine2002":  ("American Fork", "UT", "USA"),
    "alpine97":    ("American Fork", "UT", "USA"),
    "alpine98":    ("American Fork", "UT", "USA"),
    "ktvx98":      ("Salt Lake City", "UT", "USA"),
    "antelopeisland99": ("Antelope Island State Park", "UT", "USA"),
    "lava2000":    ("Lava Hot Springs", "ID", "USA"),
    "moab2001":    ("Moab", "UT", "USA"),
    "zion2000":    ("Springdale", "UT", "USA"),
    "summitpoint2000": ("Summit Point", "WV", "USA"),
    "summitpoint2001": ("Summit Point", "WV", "USA"),
    "pittsburgh2000":  ("Pittsburgh", "PA", "USA"),
    "CapeCod2001":     ("Barnstable", "MA", "USA"),
    "almostvegas2002": ("Las Vegas", "NV", "USA"),
    "vegas2001":       ("Las Vegas", "NV", "USA"),
    "chainoffools2000": ("Chicago", "IL", "USA"),
    "chainoffools2001": ("Chicago", "IL", "USA"),
    "chainoffools2002": ("Chicago", "IL", "USA"),
    "chicagodeathscoot2000": ("Chicago", "IL", "USA"),
    "chicolumbusday2002": ("Chicago", "IL", "USA"),
    "chminigolf2002":  ("Chicago", "IL", "USA"),
    "bsnoer2002":      ("Boston", "MA", "USA"),
    "bswickedpissah2001": ("Boston", "MA", "USA"),
    "bagelbrunch2002": ("Boston", "MA", "USA"),
    "buffalo2001":     ("Buffalo", "WV", "USA"),
    "buffalo2002":     ("Buffalo", "WV", "USA"),
    "amerivespa2002":  ("Denver", "CO", "USA"),
    "clownrun2001":    ("Richmond", "VA", "USA"),
    "clownrun2002":    ("Richmond", "VA", "USA"),
    "deliverance2002": ("Elkins", "WV", "USA"),
    "downndirty2001":  ("Marlinton", "WV", "USA"),
    "downndirty2002":  ("Marlinton", "WV", "USA"),
    "mayhem2001":      ("Denver", "CO", "USA"),
    "sunday092301":    ("Salt Lake City", "UT", "USA"),
    "stpats99":        ("Salt Lake City", "UT", "USA"),
    "guelphantirally2001": ("Guelph", "ON", "Canada"),
    "clowniesrevenge2002": ("Richmond", "VA", "USA"),
    "kingsclassic2001": ("Fresno", "CA", "USA"),
    "slaughterhouse2001": ("Portland", "OR", "USA"),
    "ricknifty2001":   ("Columbia", "SC", "USA"),
    "brscxmas2002":    ("Bristol", "England", "UK"),
    "cincoscoot2002":  ("San Antonio", "TX", "USA"),
    "rallyfromhell2001": ("Portland", "OR", "USA"),
    "gregkingeusa":    ("Washington", "DC", "USA"),
    "demons2002":      ("Chicago", "IL", "USA"),
}

US_STATES = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
}

TITLE_PATTERNS = [
    (r"\bChicago\b", "Chicago", "IL", "USA"),
    (r"\bBoston\b", "Boston", "MA", "USA"),
    (r"\bPittsburgh\b", "Pittsburgh", "PA", "USA"),
    (r"\bDenver\b", "Denver", "CO", "USA"),
    (r"\bSalt Lake\b", "Salt Lake City", "UT", "USA"),
    (r"\bLas Vegas\b", "Las Vegas", "NV", "USA"),
    (r"\bAtlanta\b", "Atlanta", "GA", "USA"),
    (r"\bPortland\b", "Portland", "OR", "USA"),
    (r"\bSt\.? Louis\b", "St. Louis", "MO", "USA"),
    (r"\bMoab\b", "Moab", "UT", "USA"),
    (r"\bGuelph\b", "Guelph", "ON", "Canada"),
    (r"\bCape Cod\b", "Barnstable", "MA", "USA"),
    (r"\bIsle of Wight\b", "Isle of Wight", "England", "UK"),
    (r"\bBridlington\b", "Bridlington", "England", "UK"),
    (r"\bLondon\b", "London", "England", "UK"),
    (r"\bBristol\b", "Bristol", "England", "UK"),
    (r"\bRichmond\b", "Richmond", "VA", "USA"),
    (r"\bAmerican Fork\b", "American Fork", "UT", "USA"),
    (r"\bSan Antonio\b", "San Antonio", "TX", "USA"),
    (r"\bFredericksburg\b", "Fredericksburg", "VA", "USA"),
    (r"\bTucson\b", "Tucson", "AZ", "USA"),
    (r"\bColumbus Day\b", "Chicago", "IL", "USA"),
    (r"\bMinneapolis\b", "Minneapolis", "MN", "USA"),
    (r"\bSeattle\b", "Seattle", "WA", "USA"),
    (r"\bAustin\b", "Austin", "TX", "USA"),
    (r"\bPhiladelphia\b", "Philadelphia", "PA", "USA"),
    (r"\bNashville\b", "Nashville", "TN", "USA"),
    (r"\bNew York\b", "New York", "NY", "USA"),
    (r"\bSan Francisco\b", "San Francisco", "CA", "USA"),
    (r"\bMilwaukee\b", "Milwaukee", "WI", "USA"),
    (r"\bDetroit\b", "Detroit", "MI", "USA"),
    (r"\bNew Orleans\b", "New Orleans", "LA", "USA"),
    (r"\bIndianapolis\b", "Indianapolis", "IN", "USA"),
    (r"\bBaltimore\b", "Baltimore", "MD", "USA"),
    (r"\bRaleigh\b", "Raleigh", "NC", "USA"),
    (r"\bSan Diego\b", "San Diego", "CA", "USA"),
    (r"\bSacramento\b", "Sacramento", "CA", "USA"),
    (r"\bTampa\b", "Tampa", "FL", "USA"),
    (r"\bKansas City\b", "Kansas City", "MO", "USA"),
    (r"\bHouston\b", "Houston", "TX", "USA"),
    (r"\bDallas\b", "Dallas", "TX", "USA"),
    (r"\bReno\b", "Reno", "NV", "USA"),
    (r"\bToronto\b", "Toronto", "ON", "Canada"),
    (r"\bMontreal\b", "Montreal", "QC", "Canada"),
    (r"\bVancouver\b", "Vancouver", "BC", "Canada"),
    (r"\bSavannah\b", "Savannah", "GA", "USA"),
    (r"\bAsheville\b", "Asheville", "NC", "USA"),
    (r"\bMadison\b", "Madison", "WI", "USA"),
    (r"\bBoise\b", "Boise", "ID", "USA"),
    (r"\bTulsa\b", "Tulsa", "OK", "USA"),
    (r"\bMemphis\b", "Memphis", "TN", "USA"),
    (r"\bOmaha\b", "Omaha", "NE", "USA"),
    (r"\bFresno\b", "Fresno", "CA", "USA"),
    (r"\bLos Angeles\b", "Los Angeles", "CA", "USA"),
    (r"\bOrlando\b", "Orlando", "FL", "USA"),
    (r"\bMiami\b", "Miami", "FL", "USA"),
]


def parse_location_from_slug(slug):
    parts = re.split(r"[-_]", slug.lower())
    parts = [p for p in parts if p and not re.fullmatch(r"\d{4}", p)]
    for i, part in enumerate(parts):
        if part in US_STATES and i > 0:
            city = " ".join(parts[max(0, i-2):i]).title()
            if city:
                return (city, part.upper(), "USA")
    return None


def parse_location_from_title(title):
    for pattern, city, state, country in TITLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return (city, state, country)
    return None


def geocode(city, region, country):
    if country in ("USA", "Canada"):
        q = f"{city}, {region}, {country}"
    else:
        q = f"{city}, {region}"
    params = urllib.parse.urlencode({"q": q, "format": "json", "limit": "1"})
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data:
                return (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception as e:
        print(f"    Nominatim error for {q!r}: {e}")
    return None


def main():
    if not RALLIES_DIR.exists():
        print(f"Rally data not found at {RALLIES_DIR}")
        print("Run scraper/build_data.py first.")
        return

    slugs = sorted(os.listdir(RALLIES_DIR))
    print(f"Found {len(slugs)} rally directories\n")

    skipped = succeeded = failed = 0

    for slug in slugs:
        meta_path = RALLIES_DIR / slug / "meta.json"
        if not meta_path.exists():
            continue

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        if meta.get("lat") is not None and meta.get("lng") is not None:
            skipped += 1
            continue

        title = meta.get("title", "")
        print(f"  {slug}")

        location = (
            MANUAL_LOCATIONS.get(slug)
            or parse_location_from_slug(slug)
            or parse_location_from_title(title)
        )

        if location is None:
            print(f"    -> no location found")
            failed += 1
            continue

        city, region, country = location
        print(f"    -> {city}, {region}")

        coord = geocode(city, region, country)
        time.sleep(RATE_LIMIT_SEC)

        if coord is None:
            print(f"    -> geocode failed")
            failed += 1
            continue

        lat, lng = coord
        meta["lat"] = round(lat, 6)
        meta["lng"] = round(lng, 6)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        print(f"    -> ({lat:.4f}, {lng:.4f})")
        succeeded += 1

    print(f"\nDone: {succeeded} geocoded, {skipped} already done, {failed} failed")
    print("Run 'python scraper/build_data.py' to rebuild index.json with coordinates.")


if __name__ == "__main__":
    main()