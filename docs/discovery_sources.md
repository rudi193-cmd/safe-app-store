# Discovery sources

> **Status:** Research input — third-party hosted tool directories to mine for
> catalog ideas and gap-spotting. Not SAFE apps, not kept, not provisioned, not
> promoted. Nothing here should ever carry sensitive/PII/evidentiary data — see
> each entry's caveats.
>
> Moved out of `catalog.json` in the store refit's P4
> (`docs/store_refit_plan.md`): `catalog.json` is a shelf's stock, not a
> shelf's market research. This directory belongs in `docs/`, not the catalog.

## public.tools

- **URL:** https://public.tools/
- **Type:** external-directory
- **Added:** 2026-06-19 by vishwakarma
- **Description:** Curated directory of free, no-login, browser-based tools
  (image/graphics, transcription, text-diff, encrypted notes, converters, code
  playgrounds). Mine for catalog ideas, gap-spotting, and "does a free tool for
  X already exist" lookups.
- **Caveats:** Not a SAFE app — third-party hosted tools the store does not
  control. Do NOT route sensitive/PII/evidentiary data through listed tools
  (esp. Mailinator, whose inboxes are public). 403-blocks automated fetch
  (Cloudflare); enumerate via web search or manual browse.
- **Highlighted tools:**
  - [OTranscribe](https://public.tools/tool/otranscribe) — manual audio/video
    transcription
  - [DiffNow](https://public.tools/tool/diffnow) — text/file comparison
  - [ProtectedText](https://public.tools/tool/protectedtext) — browser-encrypted
    notepad

## public-apis-live

- **URL:** https://manavarya09.github.io/public-apis-live/
- **Data URL:** https://raw.githubusercontent.com/Manavarya09/public-apis-live/main/data/apis.json
- **Type:** external-directory
- **Added:** 2026-06-19 by vishwakarma
- **Consumers:** jeles
- **Description:** Live-verified directory of 4,281 public APIs across 126
  categories, deduped from existing public-API lists and auto-checked daily for
  reachability (status up/down/unknown, httpCode, responseMs, uptimePct,
  lastChecked). Structured JSON dataset — Jeles/retrieval can filter to
  reachable + no-auth endpoints. Categories incl. Open_data (290), Government
  (110), Geocoding (117), Finance (82), Science & Math, Health, Weather.
- **Caveats:** Reachability only — does NOT functionally test endpoints;
  ~1,032 entries have unknown status. Third-party listings; verify auth/terms
  before use. Also available as npm `public-apis-live` and a Claude plugin.
- **Local mirror:** `~/Desktop/Nest/jeles/sources/public-apis-live/`
  (`apis.json`, `apis.jsonl`, `SUMMARY.json`)
- **Willow refs:** `jeles_atom: 701AD460` · `kb_atom: 0F649830`
