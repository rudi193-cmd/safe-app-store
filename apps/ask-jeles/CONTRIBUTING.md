# Contributing to Ask Jeles

Thanks for helping improve Jeles.

## Scope

Ask Jeles lives in `apps/ask-jeles/`. Changes outside that directory belong in separate PRs unless they are required for the app to run.

## Development setup

```bash
cd apps/ask-jeles
./dev.sh --demo          # offline demo, no network
pip install -e ".[dev]"    # editable install + pytest
pytest -q
```

Windows:

```powershell
.\dev.ps1 --demo
pip install -e ".[dev]"
pytest -q
```

## Pull requests

- Keep PRs focused (one concern per PR when possible).
- Run `pytest` before opening.
- Update README if behavior, keys, or install steps change.
- Do not commit secrets, `.env`, `.venv/`, or `*.egg-info/`.

## Privacy and consent

- Learning capture is opt-in per session (`Ctrl+L` in the TUI).
- Do not log or commit user queries from manual testing without redaction.
- MCP tool calls from the drawer require explicit confirmation.

## Code style

Match surrounding code: small functions, explicit names, minimal scope. Prefer tests for behavior that must not regress (demo deck, learning events, MCP discovery, trivia scrubbing).
