"""Wire the standalone ``nestor`` package into this host, once.

Call :func:`configure_nestor` before any use of the ``nestor`` cascade,
memory, or ledger. It:

  * installs :class:`~semantic_translator.nestor_store.SemanticTranslatorStore`
    as Nestor's process-wide store (documents/segments/tm_pairs all land in
    the app's ``data/translator.db``), and
  * installs the host's bilingual-pair loader
    (``learn._load_bilingual_pairs``) so ``nestor.memory.seed_from_corpus``
    seeds sealed pairs from the app's corpus, exactly as the old embedded
    ``memory.seed_from_corpus`` did.

The ledger default (``data/ledger.jsonl``) already matches the app's original
location, so no override is needed; it can still be pointed elsewhere via the
``NESTOR_LEDGER`` env var or ``nestor.set_ledger_path``.

Idempotent and cheap — safe to call at the top of every entry point.
"""
from __future__ import annotations

from nestor import memory, storage

from .learn import _load_bilingual_pairs
from .nestor_store import SemanticTranslatorStore

_configured = False


def configure_nestor() -> None:
    """Install the host store + bilingual loader into Nestor. Safe to repeat."""
    global _configured
    if _configured:
        return
    storage.set_store(SemanticTranslatorStore())
    memory.set_bilingual_loader(_load_bilingual_pairs)
    _configured = True
