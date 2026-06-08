# NASA — North America Scootering Archive

A community-owned digital archive preserving the history of North American scooter rallies from 1997 onwards. Photos, patches, stories — the record of a community.

**Source material:** scoot.net gallery, patch gallery, and calendar (2000–2014)
**Stack:** Python scraper → Cloudflare R2 → GitHub (data as JSON) → Astro static site → GitHub Pages
**Status:** Active development. Mapper running. Photos not yet uploaded.

---

## What This Is

scoot.net was the hub of North American scooter culture from roughly 1997 to 2013, when Facebook absorbed rally organizing and posting. The site went quiet but the photos stayed up — thousands of rally photos, patch scans, and event listings spanning nearly two decades.

This archive:
- Scrapes and preserves that history before it disappears
- Hosts images on Cloudflare R2 (permanent, fast, cheap)
- Lets community members claim photos, add stories, correct dates
- Picks up where scoot.net left off — ongoing events, new photos, new patches
- Will have an LLM-guided oral history feature so people can share what they remember

---

## Repository Structure

```
nasa-archive/
├── scraper/              # Python — maps scoot.net structure
│   ├── map_site.py       # Phase 1: discover all rally/photo URLs
│   ├── build_data.py     # Transforms mapper output into site data
│   ├── requirements.txt
│   └── output/           # Scraper output (gitignored)
│
├── downloader/           # Python — downloads images, uploads to R2
│   └── download.py
│
├── data/                 # Site data (JSON, committed to repo)
│   ├── index.json        # Master stats + rally list
│   └── rallies/
│       └── {slug}/
│           ├── meta.json
│           └── photos.json
│
├── site/                 # Astro static site
│   └── src/
│       ├── layouts/
│       │   └── Base.astro
│       └── pages/
│           ├── index.astro       # Homepage
│           ├── rallies.astro     # Browse all rallies
│           ├── rally/[slug].astro # Individual rally
│           ├── patches.astro     # Patch gallery
│           ├── calendar.astro    # Upcoming + past events
│           └── contribute.astro  # Claim photos, add stories
│
└── .github/
    └── workflows/
        └── deploy.yml    # Auto-deploy to GitHub Pages on push
```

---

## Running Locally

### Prerequisites
- Python 3.10+
- Node.js 20+
- A `.env` file (see below)

### 1. Map the gallery (scraper)

```bash
cd scraper
pip install -r requirements.txt
python map_site.py
```

This crawls scoot.net and writes `scraper/output/gallery_full.json`. Takes several hours for all 1,147 rallies. Saves checkpoints every 25 rallies so it can be resumed.

### 2. Build site data

```bash
python scraper/build_data.py
```

Reads `gallery_full.json`, writes `data/rallies/{slug}/` directories and `data/index.json`.

### 3. Download images to R2 (optional — requires .env)

```bash
cd downloader
pip install boto3 piexif requests python-dotenv
python download.py --phase 1   # Resolve image URLs from scoot.net
python download.py --phase 2   # Download + upload to Cloudflare R2
```

### 4. Run the site

```bash
cd site
npm install
npm run dev
```

Site runs at `http://localhost:4321`. Reads from `../data/` at build time.

---

## Environment Variables

Create a `.env` file in the repo root (never committed):

```ini
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
R2_BUCKET=nasa-archive
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_PUBLIC_URL=https://pub-b58cb742396a47e6a5953f8d499e8c35.r2.dev
```

R2 credentials are created in the Cloudflare dashboard under R2 → Manage R2 API Tokens.

---

## Data Schema

### `data/index.json`
```json
{
  "rallies": 1147,
  "total_photos_mapped": 85000,
  "patches": 0,
  "calendar_entries": 0,
  "rallies_list": [...]
}
```

### `data/rallies/{slug}/meta.json`
```json
{
  "slug": "amerivespa2002",
  "title": "Amerivespa 2002",
  "year": 2002,
  "month": 7,
  "date_rally": "2002-07",
  "photo_count": 312,
  "url": "http://scoot.net/gallery/amerivespa2002/"
}
```

### `data/rallies/{slug}/photos.json`
```json
[
  {
    "pic_id": "292230",
    "pic_url": "http://scoot.net/gallery/pic.html?pic=292230",
    "photographer": "Damn_Dirty_Dave",
    "date_rally": "2002-07",
    "date_exif": null,
    "date_canonical": null,
    "date_source": "rally_slug",
    "r2_thumb": "https://pub-b58cb742396a47e6a5953f8d499e8c35.r2.dev/gallery/200207-Damn_Dirty_Dave/292230/thumb.jpg",
    "r2_full": null
  }
]
```

**Date provenance system:**
`date_rally` — extracted from slug, reliable
`date_exif` — from image EXIF, stored but NOT trusted (camera clocks were unreliable)
`date_canonical` — human-set, authoritative
`date_source` — which field is authoritative (`rally_slug` | `exif` | `human`)

---

## Deployment

Pushes to `main` automatically build and deploy via GitHub Actions (`.github/workflows/deploy.yml`).

**GitHub Pages setup (one-time):**
Settings → Pages → Source → GitHub Actions

**Custom domain:** Update `site/public/CNAME` with your domain, then add a CNAME DNS record pointing to `rudi193-cmd.github.io`.

---

## Planned Features

- [ ] User authentication (Supabase — GitHub OAuth + email magic link)
- [ ] Photo claiming — tag yourself, correct names/dates
- [ ] Oral history LLM — guided story capture with per-user persistent memory
- [ ] Interactive rally map — geographic pins for all past + upcoming rallies
- [ ] User rally tracker — "where you've been, where you're going"
- [ ] Upcoming rally calendar — community-submitted, sortable by region/date
- [ ] Patch gallery — full R2-hosted patch image archive
- [ ] Corporate sponsorship / PBS-style funding model

---

## Contributing

Contributions to the archive data, site code, and community features are welcome. The archive belongs to the community that lived it.

Issues and PRs: [github.com/rudi193-cmd/nasa-archive](https://github.com/rudi193-cmd/nasa-archive)
