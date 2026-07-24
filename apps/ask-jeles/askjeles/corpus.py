"""Compatibility shim — the verified-nugget corpus now lives in the standalone
`jeles` package.

The organ was extracted from Ask Jeles into its own installable repo
(https://github.com/rudi193-cmd/jeles); Ask Jeles is now a *consumer*. This
module aliases itself to `jeles.corpus` so every existing
`from askjeles import corpus` / `askjeles.corpus.<name>` call-site keeps
working unchanged — same functions, same module-level state, same SOIL store
path (`WILLOW_STORE_ROOT/ask_jeles_corpus/store.db`).

Import behavior, storage schema, and the public API are all unchanged; only
the code's home moved. See docs/design/verified-corpus.md.
"""

from __future__ import annotations

import sys

from jeles import corpus as _corpus

# Make `askjeles.corpus` *be* `jeles.corpus` — one module object, one set of
# module-level globals (the sqlite connection cache, the collection names).
# This keeps white-box call-sites and tests that touch module state faithful.
sys.modules[__name__] = _corpus
