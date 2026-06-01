# Ratatosk

Sovereign Claude Code replacement. Direct Anthropic API, full tool loop, JSONL sessions, MCP client, Grove-wired.

**b17:** L3178  ΔΣ=42

## Run

```bash
python -m ratatosk.crown                    # default (claude-sonnet-4-6)
python -m ratatosk.crown --trust            # auto-approve tools
python -m ratatosk.crown --mcp              # connect to sap_mcp.py
python -m ratatosk.crown --persona gerald   # load persona
python -m ratatosk.crown --local            # Ollama (llama3.2:1b)
```

## Env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | — | Required for cloud mode |
| `WILLOW_ROOT` | `~/github/willow-1.9` | Willow repo root (CLAUDE.md, personas, sap_mcp.py) |
| `RATATOSK_SESSION_DIR` | `~/.claude/projects/...` | JSONL session output dir |
| `RATATOSK_MCP_PATH` | `$WILLOW_ROOT/sap/sap_mcp.py` | MCP server path |
| `RATATOSK_GROVE_CHANNEL` | _(disabled)_ | Grove channel for session events |
| `WILLOW_AGENT_NAME` | `ratatosk` | Grove sender identity |

## Grove wiring

Set `RATATOSK_GROVE_CHANNEL=general` to post session start/end events to Grove.

Listener shape (receive tasks from Grove → run as sessions) is stubbed in `grove.py` — not yet built.

## SAFE app

Registered in `safe-app-store/apps/ratatosk/safe-app-manifest.json`.  
Permissions: `local_llm`, `filesystem_write`, `willow_kb_read`, `willow_kb_write`.
