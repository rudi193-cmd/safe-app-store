# nest-seed

Portable Nest bootstrap. Drop a folder of personal files — photos, PDFs, scans,
documents, receipts, notes — and get a structured SQLite Nest DB out the other end.
No fleet dependency. No Postgres. Runs anywhere Python runs.

## What it does

1. **Walks** any folder recursively
2. **Extracts** text by file type (tesseract for images, pdfplumber for PDFs, passthrough for text/code)
3. **Classifies** fragments — pure-regex by default; with `--llm`, a local Ollama
   model reads the *content* and assigns a topical category (legal, journal,
   knowledge, financial, code, …) instead of guessing from the filename
4. **Writes** a portable SQLite Nest DB: `sources` + `fragments` + `nest_meta`

The DB is canonical — apps read it, never mutate it. Fleet promotion (Willow KB) is the next layer.

## Classification: regex vs. local AI

By default classification is pure regex/keyword heuristics — fast, offline, no
models. Good for a first pass, but ambiguous files land as `document`/`unknown`
and keyword matches misfire (a file with the word "total" looks like a receipt).

Pass `--llm` to classify by content using a **local** Ollama daemon — no cloud,
no API keys. A small text model (default `llama3.2:3b`) assigns the fragment
type, a topical category, and a one-line summary; a vision model
(default `qwen2.5vl:7b`) reads images. If Ollama is unreachable or a model is
missing/too large for available memory, each file falls back to the regex path —
so `--llm` never *fails*, it degrades.

```bash
python apps/nest-seed/app.py --folder ~/life-dump --owner "Your Name" --llm --dry-run
# override models / host:
NEST_TEXT_MODEL=llama3.1:8b OLLAMA_HOST=http://localhost:11434 \
  python apps/nest-seed/app.py --folder ~/life-dump --llm --db ~/Desktop/Nest/seed.db -v
```

Requires a running [Ollama](https://ollama.com) with at least the text model pulled
(`ollama pull llama3.2:3b`); the vision model is optional (`ollama pull qwen2.5vl:7b`).

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
