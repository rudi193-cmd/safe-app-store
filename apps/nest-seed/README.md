@markdownai v1.0

# nest-seed

Portable Nest bootstrap. Drop a folder of personal files — photos, PDFs, scans,
documents, receipts, notes — and get a structured SQLite Nest DB out the other end.
No fleet dependency. No Postgres. Runs anywhere Python runs.

## What it does

1. **Walks** any folder recursively
2. **Extracts** text by file type (tesseract for images, pdfplumber for PDFs, passthrough for text)
3. **Classifies** fragments heuristically — person names, dates, locations, events, receipts
4. **Writes** a portable SQLite Nest DB: `sources` + `fragments` + `nest_meta`

The DB is canonical — apps read it, never mutate it. Fleet promotion (Willow KB) is the next layer.

## Quick start

```bash
# Dry run — see what would be extracted, no DB written
python -m apps.nest_seed --folder ~/life-dump --owner "Your Name" --dry-run

# Live run
python -m apps.nest_seed --folder ~/life-dump --db ~/Desktop/Nest/seed.db --owner "Your Name" -v
```

## Dependencies (optional — graceful degradation if missing)

| Package | Used for |
|---------|----------|
| `pytesseract` + `tesseract` | Image OCR (.jpg .png .tiff .webp) |
| `Pillow` | Image loading |
| `pdfplumber` | PDF text extraction |
| `pdf2image` + `poppler` | Scanned PDF fallback |
| `python-docx` | .docx files |

Plain text files (.txt .md .csv .tex .lean) work with no extra dependencies.

```bash
pip install pytesseract Pillow pdfplumber pdf2image python-docx
sudo apt install tesseract-ocr poppler-utils   # or brew install
```

## DB schema

```
sources    — original files (path, hash, ocr_method, status)
fragments  — classified pieces (type, content, confidence, date_ref)
nest_meta  — owner, created_at, description
```

Fragment types: `person` `date` `location` `event` `document` `photo` `receipt` `note` `unknown`

## Relation to the fleet

The Nest DB is L1 — canonical, read-only for consumers.
Apps write sidecars only. Fleet owns KB promotion.
This tool seeds L1 from nothing.

## Next steps (stubs, not yet built)

- `promote.py` — push fragments to Willow KB via `kb_ingest`
- `watch.py` — inotify watcher for a live drop folder
- `query.py` — simple CLI search over the Nest DB
