# _archived/

Retired code, kept for reference (archive, don't delete).

## `safe_integration.py` — dead direct-`store.db` reader

A "portless Willow helpers" stub identical in spirit to the one retired from
private-ledger. Its `query()` reached **directly** into Willow's SOIL SQLite
(`~/.willow/store/knowledge/store.db`, `SELECT data FROM records WHERE data
LIKE ?`) — the coupling CLAUDE.md rule #1 forbids and willow-mcp's
`bundle/hooks/pre_tool_use.py` blocks. The rest (`ask`/`ask_raw`/`_drop`) were
hardcoded "not available in portless mode" no-ops, and `contribute()` staged a
file to a local intake queue.

**Nothing in the app imported it** (grep-confirmed): public-ledger's data comes
from external public-record APIs (USASpending, ProPublica) via `src/app/
sources/`, not the Willow KB. So the file was dead, and reaching into another
service's DB was the anti-pattern regardless. Retired here.

When public-ledger grows a genuine Willow-KB read (e.g. for the cross-app
entity-graph or shared provenance work), it should use the injected
`willow_read` seam pattern established in `apps/the-binder/willow_read.py`
(prefers `knowledge_search`; never a direct DB read).
