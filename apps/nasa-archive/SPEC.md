# NASA Archive — Product Spec v1

## What This Actually Is

**Three things, not one.**

The current repo mashes together what should be separate projects under one landing page:

### 1. NASA — North America Scootering Archive
The **photo gallery and oral history** site. This is the main product.
- 1,147 rallies indexed, 85K+ photos mapped
- Oral history via Riggs (Prof. Riggs, Applied Reality Engineering, UTETY)
- Community memory preservation — "Names Given Not Chosen", "Corrections Not Erasure"
- Visual language: **scoot.net gallery aesthetic** — clean, photo-forward, functional
- Think: the scoot.net gallery as it was, but alive again and connected to a knowledge graph

### 2. ScooterBBS Revival
A **separate project** that happens to live in this folder.
- Scraped data from scooterbbs.com via Wayback Machine (already in `scraper/bbs_scraper.py`)
- Forum/BBS aesthetic — threaded conversations, community voice
- Different UI, different purpose — conversation archive vs photo archive
- This is a preservation/revival project, not part of NASA's gallery

### 3. Landing Page
One page that links to both (and future projects):
- NASA Gallery → photo archive + oral history + Riggs
- ScooterBBS → forum archive / revival
- Possibly more as they emerge

---

## The Mistake That Was Made

The scooterbbs.com *aesthetic* (dark, dense, forum-style) leaked into the NASA gallery UI.
NASA should look like **scoot.net** — a photo gallery site. Clean. Photos are the point.
The BBS aesthetic belongs on the BBS project.

---

## Design Direction

### NASA Gallery
- **Reference:** scoot.net gallery pages (Wayback), modern photo archive sites
- Photo-forward — large thumbnails, photographer credits, rally context
- Cream/warm tones, not harsh dark-mode-dev-page
- Minimal chrome — the photos and stories are the content
- Rally pages are the hero — browse by year, by region, by photographer
- Riggs chat panel: warm, workshop-feeling, not clinical

### ScooterBBS
- **Reference:** scooterbbs.com via Wayback Machine
- Forum aesthetic — threaded posts, signatures, post counts
- Nostalgic but functional — honor the original look
- Separate project, separate route, separate vibe

### Landing Page
- Simple. Two doors. Pick one.
- Could be as simple as a split screen or two cards
- No hero section, no marketing — the community knows what this is

---

## Architecture

### What exists now
```
User → Astro static site (GitHub Pages) → JSON data files (in repo)
User → Oral chat panel → local_oral_chat.py (Riggs) → fleet LLM
```

### What needs to exist
```
                    ┌─────────────────────────┐
                    │     Landing Page         │
                    │  nasa-archive.pages.dev  │
                    └──────┬──────────┬────────┘
                           │          │
                    ┌──────▼──┐  ┌────▼───────┐
                    │  NASA   │  │ ScooterBBS  │
                    │ Gallery │  │   Revival   │
                    └────┬────┘  └─────────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         Browse      Talk to     Write
         Photos      Riggs      Stories
              │          │          │
              ▼          ▼          ▼
         Static      Fleet LLM   Postgres
         JSON/R2     (free)      (oral_stories)
```

### Data stays local — ALWAYS
- All notes, tags, session data: saved on the user's own machine
- "I Was There" / "I Shot These" / oral history transcripts → local storage
- No central server. No cloud database holding everyone's data.
- Your archive is YOUR archive. It runs on YOUR machine.

### Architecture: Peer-to-Peer, Not Client-Server

**There is no central server.** Each user boots their own local server.
The mesh connects users directly — user-to-user, not user-to-server-to-user.

```
     ┌──────────┐         ┌──────────┐
     │ User A   │◄───────►│ User B   │
     │ (local   │  P2P    │ (local   │
     │  server) │  mesh   │  server) │
     └────┬─────┘         └────┬─────┘
          │                    │
          │    ┌──────────┐    │
          └───►│ User C   │◄──┘
               │ (local   │
               │  server) │
               └──────────┘
```

Each node:
- Runs its own Riggs (via fleet LLM — free)
- Has its own local database (Postgres or SQLite)
- Stores its own photos, stories, tags, oral histories
- Connects to peers to share/discover/sync — with consent

**Bridge Ring = the P2P mesh itself.** Not a pipe to a central DB.
When you "connect your Bridge Ring," you're joining the mesh —
your node becomes visible to other nodes, and you choose what to share.

### What the static site does
- GitHub Pages / Cloudflare Pages hosts the **app shell**
- The app shell is the installer/launcher — gets you set up
- Once running, your local server IS the app
- The static site also serves as the read-only gallery for non-participants
  (browse photos, read stories — but can't contribute without running a node)

### What each local node runs
- `local_oral_chat.py` → Riggs (fleet LLM, no cost)
- Local database (oral history, tags, claims, stories)
- P2P discovery + sync layer (WebRTC / libp2p / similar — TBD)
- Full rally data (JSON from repo — everyone has the same base dataset)

### Hosting: solved by not hosting
- No server to pay for
- No server to go down
- No company to sell the data
- No platform to change the terms
- The archive survives because the people carrying it survive
- "The library is always on fire. So everyone carries a copy."

### Open: P2P technology choice
- **WebRTC** — browser-native, works for real-time peer connections
- **libp2p** — more robust, used by IPFS, handles NAT traversal
- **Hypercore / Hyperswarm** — designed for P2P data sync, append-only logs
- **Gun.js** — decentralized graph DB, works in browser
- Need a signaling server for initial peer discovery (lightweight, cheap/free)
  - This is the ONE piece that could be centralized — just for "who's online"
  - Could use a free WebSocket service or a simple Cloudflare Worker

---

## Pages

### Landing Page (`/`)
- Two doors: NASA Gallery, ScooterBBS
- Community stats if we want them
- No login required

### NASA Gallery (`/gallery` or `/rallies`)
- Browse all 1,147+ rallies
- Filter by year, region
- Each rally card: title, year, photo count, thumbnail if available

### Rally Detail (`/rally/{slug}`)
- Hero: rally name, date, photo count, photographer count
- Photo grid grouped by photographer
- "I Was There" / "I Shot These" claim buttons
- Oral History section — talk to Riggs
- Story submission panel
- Community stories (loaded from DB)
- Download session data as JSON

### Riggs Chat (panel on rally pages)
- Slide-up panel, not a separate page
- Prof. Riggs voice via fleet LLM
- Rally-specific context injected
- Session saved locally, contribute optionally

### Patches (`/patches`)
- Grid of patch scans (when available)
- Upload your own

### Map (`/map`)
- Geographic pins for all rallies
- Click to browse

### Calendar (`/calendar`)
- Upcoming rallies (community-submitted)
- Past rallies by month

### Profile (`/profile`)
- Requires account
- Your tagged photos, your stories, your rally attendance
- Bridge Ring connection status

---

## Immediate Priority (High Rollers 2026)

People are posting photos on Facebook RIGHT NOW from High Rollers (last weekend).
The window for warm oral history capture is open.

**MVP to share this week:**
1. Landing page that doesn't look like a dev page
2. Rally browse page that works and looks good
3. Rally detail page with working Riggs chat
4. Add High Rollers 2026 to the index (not yet there — last indexed: 2012)
5. Riggs needs to be reachable — either via tunnel or edge function

**Not needed for MVP:**
- ScooterBBS revival (separate timeline)
- User accounts / Bridge Ring (future)
- Patch gallery (no patches scanned yet)
- Map (nice to have, not blocking)

---

## Open Questions

1. **P2P technology:** WebRTC, libp2p, Hyperswarm, Gun.js — which fits best?
   - WebRTC = simplest for browser-to-browser
   - Hyperswarm = best for data sync (append-only logs, like oral histories)
   - Signaling server needed either way (lightweight — just "who's online")
2. **Local server packaging:** How does a non-technical person boot their node?
   - Electron app? Docker container? Simple Python script + installer?
   - `local_oral_chat.py` already works — but need to package it
3. **ScooterBBS:** Same repo or split? (Separate project, could be separate repo)
4. **Domain:** nasa-archive.pages.dev? scooterarchive.org?
5. **High Rollers 2026:** Manual index entry + FB photo collection?
6. **Sync model:** What gets shared between peers?
   - Stories? Photos? Tags? All opt-in per type?
   - Conflict resolution when two people tell different versions of the same rally?
   - (This is exactly what Nova handles — narrative stabilization)
7. **~~Identity without accounts~~** — RESOLVED: Simple email + password registration.
   Credentials stored locally on the user's machine. Not an account on a central server.
   It's an identity they present to the mesh when they choose to share their Bridge Ring.
   No sharing = no registration required. Browse, tag, talk to Riggs — all anonymous/local.
