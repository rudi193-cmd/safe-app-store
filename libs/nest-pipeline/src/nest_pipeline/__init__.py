"""nest_pipeline — the shared Nest content pipeline for hosted apps.

Box audit A4: the Nest seeder core was duplicated byte-for-byte between
``safe-app-store/apps/nest-seed`` and ``willow-mcp``'s Nest engine. Both are
twins on one portable SQLite schema; the danger of two copies is silent drift.
This package is the single canonical home for that shared core:

  ocr        text/OCR extraction by file type (lazy tesseract / pdfplumber)
  ingest     walk a folder, extract, classify, write the Nest DB
  classify   tiered hybrid classifier (regex -> embeddings -> generative LLM)
  embed      local embedding seam (nomic-embed-text via Ollama)
  llm        local LLM seam (text + vision, via Ollama)
  taxonomy   category seed phrases -> cached centroids
  selflearn  self-learning corrections store
  secrets    the credential guard (redacts secret-shaped fragments)
  db         the portable SQLite Nest schema (sources/fragments/nest_meta)

Third-party extractors (tesseract, pdfplumber, Pillow, pdf2image, python-docx)
and the Ollama HTTP calls are imported lazily inside functions, so importing
this package is stdlib-only and egress-free. Apps that consume it
(``from nest_pipeline import ...``) keep their own app-specific layers
(bridge, digest, ask, curate, the CLI) outside this core.
"""
