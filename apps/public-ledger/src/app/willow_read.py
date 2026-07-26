# b17: SAPS1  ΔΣ=42
"""willow_read — public-ledger's KB-read seam.

Now a thin re-export of the shared, canonical ``willow_read`` library (box audit
A5): the gated-only ``knowledge_search`` read, with no raw shared-store fallback
(B3). The implementation used to live here and was hand-rolled again in the-binder
and private-ledger; it now lives once in libs/willow-read. This module is kept as
the app's stable import point, so ``app.willow_read`` and its callers/tests are
unchanged.
"""
from willow_read import (  # noqa: F401  (re-export)
    KnowledgeClient,
    active_backend,
    available,
    get_client,
    search,
    set_client,
)

__all__ = [
    "KnowledgeClient", "set_client", "get_client",
    "active_backend", "available", "search",
]
