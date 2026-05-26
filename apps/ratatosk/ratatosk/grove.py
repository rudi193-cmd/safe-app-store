"""
grove.py — Grove wiring for Ratatosk.
b17: D7CD0  ΔΣ=42

Observability: posts session start/end events to Grove.
Set RATATOSK_GROVE_CHANNEL (e.g. "general") to enable.

Send path: uses WILLOW_PG_URL if set, else WILLOW_PG_DB/WILLOW_PG_USER.
TODO: route through SAP MCP grove_send_message instead of psycopg2 direct.
      Wire by passing mcp_call from main() once --mcp is the norm.

Listener shape (future): RATATOSK_GROVE_LISTEN=1 watches the channel for
incoming task messages and dispatches them as CLI sessions. Not yet built.
"""
import os

_CHANNEL = os.environ.get("RATATOSK_GROVE_CHANNEL", "")
_PG_URL = os.environ.get("WILLOW_PG_URL", "")
_DB = os.environ.get("WILLOW_PG_DB", "willow")
_USER = os.environ.get("WILLOW_PG_USER", os.environ.get("USER", ""))
_SENDER = os.environ.get("WILLOW_AGENT_NAME", "ratatosk")


def _send(content: str) -> None:
    if not _CHANNEL:
        return
    try:
        import psycopg2
        conn = psycopg2.connect(_PG_URL) if _PG_URL else psycopg2.connect(dbname=_DB, user=_USER)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT id FROM grove.channels WHERE name=%s LIMIT 1", (_CHANNEL,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "INSERT INTO grove.messages (channel_id, sender, content) VALUES (%s, %s, %s)",
                (row[0], _SENDER, content),
            )
        conn.close()
    except Exception:
        pass


def session_started(session_id: str, model: str) -> None:
    _send(f"[ratatosk] session started — {session_id[:8]} model={model}")


def session_ended(session_id: str, turns: int, jsonl_path: str) -> None:
    _send(f"[ratatosk] session ended — {session_id[:8]} turns={turns} jsonl={jsonl_path}")
