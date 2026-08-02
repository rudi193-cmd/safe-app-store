# playgate

Browser shells for **Nest Playgate** — curated Waydroid installs with a parent disposition loop.

The **host daemon** (Python API, disposition log, adb install hook) lives in the canonical prototype:

`~/Desktop/Nest/playgate/`

This store app holds the **kid** and **parent** static UI only (`kid/`, `parent/`). Serve them via the Nest host:

```bash
cd ~/Desktop/Nest/playgate && ./serve.sh
```

Do not open these HTML files as `file://` — use the host so `/api/*` routes work.

## Store record

- Major: `browser`
- State: `building` until CI is added
- License: Apache-2.0

See Nest `README.md` for Waydroid prerequisites and F-Droid optional path (`docs/FDROID.md`).
