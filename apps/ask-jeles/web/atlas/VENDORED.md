# The Catalog — vendored from Atlas of Knowledge

This directory is a **vendored copy** of a third-party project, reskinned as
"The Catalog" — the visual, browsable prerequisite map inside Ask Jeles.

## Upstream

- **Project:** Atlas of Knowledge
- **Author:** Ethan Vieira
- **Source:** https://github.com/EthanVieira/atlas-of-knowledge
- **Live original:** https://ethanvieira.github.io/atlas-of-knowledge/
- **Vendored at commit:** `aaa2ddaac402aac012626311ea36cc3009b782bf`
- **Vendored on:** 2026-07-13

## Licenses (preserved, unchanged)

- **Code** (HTML/CSS/JS, `scripts/validate.js`) — MIT. See [`LICENSE`](LICENSE).
- **Course data** (everything under `js/data/`) — CC BY-SA 4.0. See
  [`LICENSE-DATA.md`](LICENSE-DATA.md).

Attribution to Ethan Vieira is retained in-app (the deskbar credit at the
bottom-left of the map) and here. The course data is used **unmodified**; if it
is ever edited within this vendored copy, those edits must remain under
CC BY-SA 4.0 (share-alike) and the change noted below.

## What we changed (and only this)

The upstream engine and data are untouched. Our changes are additive and
cosmetic, so future upstream syncs stay easy:

1. `index.html` — retitled to "The Catalog"; rebranded the header
   (`Atlas of Knowledge / Constellations of Learning` → `The Catalog /
   The Stacks, made visible`); loaded the desk fonts and `css/jeles-skin.css`
   after `css/styles.css`; added the `#jeles-deskbar` (back-to-desk link +
   author credit).
2. `css/jeles-skin.css` — **new file.** Overrides the Atlas palette custom
   properties to Ask Jeles' exact desk palette. The upstream `css/styles.css`
   is not forked.
3. `README.md` → `UPSTREAM-README.md` — the upstream README, kept for reference.

No changes to `js/**` or `js/data/**`.

## Course data modifications

None. (Record any future edits to `js/data/**` here, per CC BY-SA 4.0.)

## Re-syncing from upstream

```bash
git clone https://github.com/EthanVieira/atlas-of-knowledge.git
# copy index.html, favicon.svg, css/styles.css, js/**, scripts/, package.json
# then re-apply the two additive changes above (skin link + brand + deskbar).
```
