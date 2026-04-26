# llmphysics-bot

A Devvit app for [r/LLMPhysics](https://www.reddit.com/r/LLMPhysics/) built on the Devvit Web (server) architecture.

## What it does

### `!define <term>`
Listens for comments containing `!define` and replies with a Wikipedia summary of the requested term. Only responds to science-related topics (validated against Wikipedia categories). Can be triggered two ways:

- **Prefix mode** — comment starts with `!define quantum entanglement`
- **Summon mode** — comment mentions `u/llmphysics-bot` and contains `!define`

### Weekly Mod Digest
A scheduled job that reads a wiki page (`mod-digest` by default), posts it as a stickied distinguished post, then resets the wiki page for the following week. Schedule is configurable via the app settings panel.

### Heartbeat
Runs every 5 minutes. Re-syncs the digest schedule in case settings have changed since the last run.

---

## Architecture

Built on **Devvit Web** (`@devvit/web`) using **Hono** as the server framework. All logic lives in `src/server/index.ts`, which compiles to CommonJS via `tsc`.

```
devvit/
├── devvit.json          # App config, permissions, triggers, scheduler, settings
├── package.json
├── tsconfig.json
├── assets/
│   └── icon.png         # Snoo scientist — r/LLMPhysics mascot
└── src/
    └── server/
        └── index.ts     # All bot logic (Hono server)
```

### Key dependencies
| Package | Purpose |
|---|---|
| `@devvit/reddit` | Reddit API client |
| `@devvit/redis` | Redis key-value storage |
| `@devvit/web` | Server framework, types, context |
| `hono` | HTTP server / routing |

---

## Configuration

Once installed, moderators can configure the bot via the **Install Settings** panel in mod tools. No wiki page editing required.

| Setting | Description | Default |
|---|---|---|
| Bot username | The bot's Reddit username | `llmphysics-bot` |
| Allowed category keywords | Comma-separated list of Wikipedia category keywords that count as on-topic | `physics,mathematics,chemistry,...` |
| Blocked terms | Comma-separated list of terms the bot should refuse to define | _(empty)_ |
| Digest wiki page | Name of the wiki page to read for the weekly digest | `mod-digest` |
| Digest schedule | Cron expression for when to post the digest | `0 0 * * 0` (Sundays midnight) |
| Digest post title | Title of the weekly digest post | `Weekly Mod Digest` |
| Summary sentences | Number of sentences in `!define` replies | `3` |

Cron expressions and sentence counts are validated on save — invalid values will show an error before being accepted.

---

## Development

### Prerequisites
- Node.js 20+
- Devvit CLI: `npm install -g devvit`

### Setup
```bash
cd devvit
npm install
```

### Build
```bash
npm run build
```

### Playtest (live dev against the subreddit)
```bash
devvit playtest r/LLMPhysics
```

### Upload
```bash
npm run upload
```

---

## Permissions required
- `reddit` (moderator scope) — post, comment, sticky, distinguish, read/write wiki
- `http` — fetch requests to `en.wikipedia.org`
- `redis` — caching digest job IDs and cron state

---

## History

Originally written by [rudi193-cmd](https://github.com/rudi193-cmd) as a Devvit Blocks app using the legacy `devvit.yaml` configuration. Migrated to the Devvit Web server architecture by [allhailseizure](https://github.com/allhailseizure).

The legacy version is preserved in `(DEPRECATED) devvit/` for reference.
