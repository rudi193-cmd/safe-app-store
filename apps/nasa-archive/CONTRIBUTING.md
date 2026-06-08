# Contributing to the NASA Archive

Thanks for wanting to help. Here's how to get involved depending on what you want to do.

---

## Running the Site Locally

You only need Node.js 20+ to work on the frontend. No scraper, no Python, no R2 credentials required.

```bash
git clone https://github.com/rudi193-cmd/nasa-archive.git
cd nasa-archive/site
npm install
npm run dev
```

Site runs at `http://localhost:4321`. It reads from `../data/` which is already committed — you'll see real rally data immediately.

---

## Project Structure

```
site/src/
  layouts/Base.astro        ← Header, nav, footer — shared chrome
  pages/index.astro         ← Homepage
  pages/rallies.astro       ← Browse rallies (year filter)
  pages/rally/[slug].astro  ← Individual rally page
  pages/patches.astro       ← Patch gallery
  pages/calendar.astro      ← Events calendar
  pages/contribute.astro    ← Contribution landing page
  styles/global.css         ← Tailwind base + CSS variables
```

**Stack:** Astro (static site generator) + Tailwind CSS. No framework — just HTML, a little JS where needed.

**Deploy:** Push to `main` → GitHub Actions builds → auto-deploys to Neocities.

---

## Design

The current design is functional but rough. If you have ideas:

- **Open a Discussion** — [github.com/rudi193-cmd/nasa-archive/discussions](https://github.com/rudi193-cmd/nasa-archive/discussions) — post mockups, CSS snippets, direction thoughts
- **Open a PR** — if you want to just show the code, go for it
- **Drop a file in `design/`** — mockups, style guides, reference images

**Brand constraints (intentional):**
- Dark background: `#1a1a1a`
- Red accent: `#CC4444`
- Cream text: `#f5f0e8`
- Monospace font throughout
- Flat, no gradients or shadows — archival, not slick

The aesthetic references old-school scene zines and scooter club patches more than modern web design. Gritty is correct. Sterile is wrong.

---

## Content Contributions

You don't need to know how to code to contribute to the archive:

- **Claim a photo** — tag yourself or someone you recognise
- **Add a story** — what you remember about a rally
- **Submit a patch scan** — scan or photograph patches you have
- **Add a rally** — upcoming events, or past ones we're missing

These go through the `/contribute` page (auth required once that's built).

---

## What's Being Built

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full technical picture and [open issues](https://github.com/rudi193-cmd/nasa-archive/issues) for what's actively being worked on.

Short version of what's next:
- User auth (Supabase — GitHub OAuth + email magic link)
- Photo claiming
- Oral history LLM with per-user memory
- Interactive rally map
- Ongoing rally calendar

---

## Questions

Open a [Discussion](https://github.com/rudi193-cmd/nasa-archive/discussions) or file an [Issue](https://github.com/rudi193-cmd/nasa-archive/issues). The community owns this — nothing is too small to bring up.
