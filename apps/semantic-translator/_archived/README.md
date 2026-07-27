# Archived: embedded `nestor` (removed)

This directory once held an **embedded** copy of Nestor that lived at
`semantic_translator/nestor/`. The copy has been **removed** (box audit A11 — a
dead, duplicated Nestor; nothing imported it). The app consumes the standalone
[`rudi193-cmd/Nestor`](https://github.com/rudi193-cmd/Nestor) package instead:

- `semantic_translator/nestor_store.py` — `SemanticTranslatorStore` implements
  Nestor's `Storage` Protocol over the app's `semantic_translator/db.py`
  (documents, segments, and the verbatim-ported `tm_pairs` translation memory).
- `semantic_translator/nestor_wiring.py` — `configure_nestor()` installs that
  store and the host's bilingual-pair loader (`learn._load_bilingual_pairs`)
  into the package via `nestor.storage.set_store` / `nestor.memory.set_bilingual_loader`,
  and runs at each entry point before any Nestor use.

Do not re-embed a copy — fix Nestor upstream and repin the dependency in
`pyproject.toml`.
