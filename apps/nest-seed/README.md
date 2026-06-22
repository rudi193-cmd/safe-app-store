# nest-seed

Portable Nest bootstrap. Drop a folder of personal files — photos, PDFs, scans,
documents, receipts, notes — and get a structured SQLite Nest DB out the other end.
No fleet dependency. No Postgres. Runs anywhere Python runs.

## What it does

1. **Walks** any folder recursively
2. **Extracts** text by file type (tesseract for images, pdfplumber for PDFs, passthrough for text/code)
3. **Classifies** fragments by *meaning* — a tiered cascade (regex facts -> local embeddings -> generative LLM) assigns a topical category (legal, journal, knowledge, financial, etc.) from content, not the filename

4. **Writes** a portable SQLite Nest DB: `sources` + `fragments` + `nest_meta`

The DB is canonical — apps read it, never mutate it. Fleet promotion (Willow KB) is the next layer.

## Classification: a three-tier cascade

Files are classified cheapest-tier-first; each tier only handles what the
cheaper one couldn't, and every tier degrades gracefully if its model is absent.

1. **regex** — deterministic facts (dates, titled names). Free, offline. Also
   the final fallback when no model is available.
2. **embeddings** *(on by default)* — semantic classification via a local
   `nomic-embed-text`. The document is embedded and matched to the nearest
   **category centroid** by cosine similarity; the score *is* the confidence.
   Fast (~ms/file), local, deterministic. Handles the confident majority. This
   is real semantic matching, not keyword lookup — a file about "totals" is no
   longer mistaken for a receipt.
3. **generative** *(`--llm`)* — a local text model (`llama3.2:3b`) reads the
   text, and a vision model (`qwen2.5vl:7b`) reads images. The text model fires
   **only on the uncertain tail** (low similarity, or a tied top-2) and is
   handed the embedding's top candidates as a constrained choice — faster and
   more accurate than free-form labeling.

So `--llm` doesn't classify every file; the embedding tier resolves the easy
ones in milliseconds and the expensive model is spent only where the geometry
is genuinely ambiguous. Categories live in `taxonomy.py` as seed phrases →
centroids (cached on disk). Thresholds are tunable via `NEST_EMBED_CONFIDENT`,
`NEST_EMBED_GAP`, and `NEST_EMBED_FLOOR`.

```bash
# embeddings only (fast, no generative model needed):
python apps/nest-seed/app.py --folder ~/life-dump --owner "You" --dry-run

# full cascade (embeddings + LLM escalation on the uncertain tail):
python apps/nest-seed/app.py --folder ~/life-dump --owner "You" --llm --dry-run

# disable the embedding tier entirely:
python apps/nest-seed/app.py --folder ~/life-dump --no-embed --llm --dry-run
```

Requires a running [Ollama](https://ollama.com): `ollama pull nomic-embed-text`
(embedding tier) and optionally `ollama pull llama3.2:3b` / `qwen2.5vl:7b`
(generative tier). Without any of them, classification falls back to regex.

## Quick start

```bash
# Dry run — see what would be extracted, no DB written
python apps/nest-seed/app.py --folder ~/life-dump --owner "Your Name" --dry-run

# Live run
python apps/nest-seed/app.py --folder ~/life-dump --db ~/Desktop/Nest/seed.db --owner "Your Name" -v
```

## Dependencies (optional — graceful degradation if missing)

| Package | Used for |
|---------|----------|
| `pytesseract` + `tesseract` | Image OCR (.jpg .png .tiff .webp) |
| `Pillow` | Image loading |
| `pdfplumber` | PDF text extraction |
| `pdf2image` + `poppler` | Scanned PDF fallback |
| `python-docx` | .docx files |
| Ollama (`--llm`) | Local AI content classification |

Plain text and source files (.txt .md .csv .json .py .sh .js .html .xml …) work with no extra dependencies.

```bash
pip install pytesseract Pillow pdfplumber pdf2image python-docx
sudo apt install tesseract-ocr poppler-utils   # or brew install
```

## DB schema

```
sources    — original files (path, hash, ocr_method, status)
fragments  — classified pieces (type, content, confidence, date_ref, label)
nest_meta  — owner, created_at, description
```

Fragment types: `person` `date` `location` `event` `document` `photo` `receipt` `note` `unknown`

With `--llm`, the topical category (legal, journal, knowledge, narrative, specs,
code, correspondence, financial, education, personal, media, config, data, other)
is stored in the fragment `label` field.

## Relation to the fleet

The Nest DB is L1 — canonical, read-only for consumers.
Apps write sidecars only. Fleet owns KB promotion.
This tool seeds L1 from nothing.

## Next steps (stubs, not yet built)

- `promote.py` — push fragments to Willow KB via `kb_ingest`
- `watch.py` — inotify watcher for a live drop folder
- `query.py` — simple CLI search over the Nest DB
