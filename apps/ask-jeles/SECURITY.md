# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting

Please open a [GitHub Security Advisory](https://github.com/rudi193-cmd/safe-app-store/security/advisories/new) or email the maintainer listed in the repository profile.

Do not include secrets, full query logs, or private documents in public issues.

## Data handling

- Search queries are processed locally where possible.
- Learning events (when enabled) store small JSON summaries, not full page bodies.
- Saved searches (`Ctrl+S`) are explicit user actions.
- MCP servers are discovered but not started until the user connects one for the session.

## Disclosure

We appreciate responsible disclosure and will acknowledge reporters when fixes ship.
