# Contributing to the Atlas of Knowledge

Thank you for helping chart the map of human knowledge. This project is
**crowd-sourced**: every course, prerequisite and learning resource in the atlas
comes from people who know their field. You don't need to be a web developer to
contribute — if you can edit a text file, you can improve the atlas.

> **TL;DR** — All the knowledge lives in plain data files under
> [`js/data/`](js/data/), one file per field. To add or fix something you edit a
> field's file, run `node scripts/validate.js`, and open a pull request.

---

## What you can contribute

Anything that makes the map more accurate, more complete, or more useful:

- **📚 Learning resources** — add a great free or paid book, course, lecture
  series or set of notes to a subject you know.
- **✍️ Descriptions & topics** — improve a subject's one-line description or the
  list of topics it covers.
- **🧩 New courses** — add a subject that's missing, with its prerequisites.
- **🌳 New fields** — add a whole discipline that isn't represented yet.
- **🔗 Prerequisites** — fix a dependency that's wrong, missing, or too strict.
- **🐛 Corrections** — fix typos, dead links, mis-attributed authors, etc.

**Domain expertise is the most valuable thing you can bring.** We would rather
have five carefully chosen resources from someone who has actually studied a
field than fifty from a web search.

---

## Three ways to contribute (easiest first)

### 1. Open an issue (no coding at all)
Not comfortable editing files? Just
[open an issue](../../issues/new/choose) describing what you'd add or change —
the subject, the resource, the prerequisite — and a maintainer will fold it in.
This is a perfectly good way to contribute.

### 2. Edit on the GitHub website
1. Open the field file you want to change under [`js/data/`](js/data/)
   (e.g. `physics.js`).
2. Click the ✏️ **pencil icon** to edit it in your browser.
3. Make your change (see the [schema](#the-data-model) below).
4. At the bottom, choose **"Create a new branch and start a pull request."**

GitHub will run the validator on your change automatically.

### 3. Work locally (best for larger contributions)
```bash
git clone https://github.com/EthanVieira/atlas-of-knowledge.git
cd atlas-of-knowledge
# edit files under js/data/ ...
node scripts/validate.js      # check your work (needs Node.js; no install step)
# then open index.html in a browser to see it live
```
There is **no build step and no dependencies** — the site is plain HTML/CSS/JS.
Just open `index.html` in any browser.

---

## The data model

Everything is in [`js/data/`](js/data/):

```
js/data/_config.js     fields (label, abbr, family, hue) + the R() helper
js/data/mathematics.js one file per field — the data you edit
js/data/...
```

Each field file registers a list of courses:

```js
registerCourses([

  {
    id:       "real-analysis",              // unique, lowercase-kebab-case
    title:    "Real Analysis",              // shown on the node
    field:    "mathematics",                // a key in FIELDS (see _config.js)
    desc:     "The rigorous foundation of calculus: limits, continuity and "
            + "integration made precise.",  // one or two sentences
    requires: ["calculus-2", "set-theory"], // prerequisite course ids (edges)
    topics:   ["Construction of ℝ", "Metric spaces", "Uniform convergence"],
    free:     [ R("Basic Analysis", "Jiří Lebl", "https://www.jirka.org/ra/") ],
    paid:     [ R("Principles of Mathematical Analysis", "Walter Rudin") ],
  },

]);
```

`R(title, author, url)` is a small helper for a resource. **`url` is optional** —
if you don't have a stable link, just cite the title and author:
`R("Principles of Mathematical Analysis", "Walter Rudin")`.

### Field of every key
| key | required | notes |
|---|---|---|
| `id` | ✅ | unique across the **whole** atlas, `lowercase-kebab-case` |
| `title` | ✅ | human-readable name |
| `field` | ✅ | a key defined in `FIELDS` in `_config.js` |
| `desc` | ✅ | one or two plain sentences |
| `requires` | ✅ | array of prerequisite `id`s (may be `[]`; may cross fields) |
| `topics` | ✅ | array of short topic strings (the collapsible dropdown) |
| `free` | ✅ | array of `R(...)` resources (may be `[]`) |
| `paid` | ✅ | array of `R(...)` resources (may be `[]`) |

**Prerequisites may point at any field.** Quantum mechanics can require
`linear-algebra`; biochemistry can require `organic-chemistry`. That's
encouraged — cross-disciplinary edges are what make the atlas a map rather than a
list. The layout and colors are computed automatically; you never position a
node by hand.

---

## Adding a whole new field

1. Add an entry to the `FIELDS` map in
   [`js/data/_config.js`](js/data/_config.js):
   ```js
   geography: { label: "Geography", abbr: "GEO", family: "social", hue: 300 },
   ```
   - `abbr` is the short badge shown on the node (≤ 5 chars).
   - `family` is one of `sciences`, `engineering`, `social`, `humanities`
     (see `FAMILIES` in the same file).
   - `hue` is an HSL hue (0–360). Pick one **inside your family's arc** so the
     field looks related to its neighbors — sciences ≈ 96–190, engineering ≈
     205–266, social ≈ 278–331, humanities ≈ 340–31. Avoid ~40–55 (reserved for
     the "completed" gold).
2. Create `js/data/<field>.js` following the pattern of the existing files.
3. Add one `<script src="js/data/<field>.js"></script>` line to
   [`index.html`](index.html), next to the other field files.

---

## Style & quality guidelines

**Accuracy first.**
- Only add resources you'd genuinely recommend. Prefer **canonical** references
  (the standard textbook, the well-known lecture notes) over the first search
  result.
- Prefer **free** resources with **stable** links: university course pages
  (MIT OCW, Stanford, Yale OYC), author-hosted PDFs and notes, and established
  open textbooks (OpenStax, LibreTexts, SEP). If a link is likely to rot, cite
  without a URL instead.
- Attribute authors correctly.

**Descriptions** — one or two sentences, plain and inviting, no marketing. Say
what the subject *is*, not why it's great.

**Topics** — 4–8 short items naming the key ideas someone will learn. They fill
the collapsible dropdown; they aren't a syllabus.

**Prerequisites** — list the *minimal* set actually needed to begin, not
everything tangentially related. Fewer, correct edges beat many loose ones. Never
create a cycle (A → B → A); the validator will reject it.

**Ids** — `lowercase-kebab-case`, stable, and descriptive
(`algebraic-topology`, not `at` or `AlgTop`). Once an id is published, other
courses may depend on it, so **don't rename ids** casually — add an alias
discussion in your PR if you must.

---

## Before you open a pull request

Run the validator:

```bash
node scripts/validate.js
```

It checks the entire catalog for the things that break the atlas:

- missing/malformed course fields
- duplicate ids
- prerequisites pointing at non-existent courses
- **dependency cycles**
- courses in undefined fields; fields missing `label`/`abbr`/`family`/`hue`
- resources with no title

The same check runs automatically on every pull request via GitHub Actions, so a
PR can't be merged with broken data. Please make sure it passes locally first.

### PR checklist
- [ ] `node scripts/validate.js` passes.
- [ ] New `id`s are unique and `lowercase-kebab-case`.
- [ ] Resources are accurate, well-attributed, and links (if any) work.
- [ ] Prerequisites are minimal and correct; no cycles.
- [ ] I opened `index.html` and my subject appears where I'd expect.

---

## Governance & credit

- Larger fields may have **field maintainers** (domain experts) who review PRs in
  their area — see [`CODEOWNERS`](.github/CODEOWNERS) if present. Want to steward
  a field? Open an issue; we'd love the help.
- Contributors are credited in [`CONTRIBUTORS.md`](CONTRIBUTORS.md). Add yourself
  in your first PR if you'd like.
- By contributing, you agree that **course data** you add is licensed under
  [CC BY-SA 4.0](LICENSE-DATA.md) and any **code** under [MIT](LICENSE). Course
  descriptions and resource lists are facts and citations; please don't paste
  copyrighted text from a source.

Questions? Open a [discussion](../../discussions) or an issue. Welcome aboard. ✦
