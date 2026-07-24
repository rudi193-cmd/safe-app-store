"""Compatibility shim — the best-effort fleet gap-forwarder now lives in the
standalone `jeles` package.

Extracted from Ask Jeles into https://github.com/rudi193-cmd/jeles; Ask Jeles
is now a consumer. This module aliases itself to `jeles.willow_mcp_client` so
every `from askjeles import willow_mcp_client` / `.forward_gap(...)` call-site
keeps working unchanged, including its module-level session state (the lazy
background loop and the retry cooldown). Defaults preserve Ask Jeles' original
app_id (`ask-jeles`) and backlog topic (`ask-jeles-corpus`).
"""

from __future__ import annotations

import sys

from jeles import willow_mcp_client as _willow_mcp_client

sys.modules[__name__] = _willow_mcp_client
