# Archived: embedded `nestor`

This directory holds the original **embedded** copy of Nestor that lived at
`semantic_translator/nestor/`. It is kept for reference only — nothing imports
it anymore.

Nestor was extracted into a standalone package (repo
[`rudi193-cmd/Nestor`](https://github.com/rudi193-cmd/Nestor)). The
semantic-translator app now **consumes** that package:

- `semantic_translator/nestor_store.py` — `SemanticTranslatorStore` implements
  Nestor's `Storage` Protocol over the app's `semantic_translator/db.py`
  (documents, segments, and the verbatim-ported `tm_pairs` translation memory).
- `semantic_translator/nestor_wiring.py` — `configure_nestor()` installs that
  store and the host's bilingual-pair loader (`learn._load_bilingual_pairs`)
  into the package via `nestor.storage.set_store` / `nestor.memory.set_bilingual_loader`.

Imports were repointed from `.nestor...` to the top-level `nestor` package, and
`configure_nestor()` runs at each entry point before any Nestor use.

Do not revive this copy — fix Nestor upstream and repin the dependency in
`pyproject.toml`.
