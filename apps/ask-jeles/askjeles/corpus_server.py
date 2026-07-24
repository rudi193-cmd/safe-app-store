"""Compatibility shim — the standalone corpus MCP server now lives in the
`jeles` package (`jeles.corpus_server`).

Kept so `python -m askjeles.corpus_server` and the `askjeles-corpus-mcp`
console script (see pyproject.toml) continue to launch the extracted server.
The server itself, its tools, and its `app_id`-on-every-tool shape are all in
https://github.com/rudi193-cmd/jeles now; Ask Jeles is a consumer.

mcp_registry.py still registers this module path as the built-in corpus
server entry, so no discovery wiring changes were needed.
"""

from __future__ import annotations

from jeles.corpus_server import main, mcp  # noqa: F401  (re-exported for parity)


if __name__ == "__main__":
    main()
