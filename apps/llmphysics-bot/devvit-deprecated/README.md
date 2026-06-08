# safe-app-llmphysics-bot

A Reddit bot for [r/LLMPhysics](https://www.reddit.com/r/LLMPhysics/) that responds to `!define <term>` commands with a 3-sentence Wikipedia summary and a link to the full article. Also posts a weekly mod digest from a wiki page.

There are **two ways to run** this bot:

| Approach | Directory | Runtime | Best for |
|---|---|---|---|
| **Python (PRAW)** | repo root | Python 3.10+ | Self-hosted on your own machine/server |
| **Devvit app** | `devvit/` | Node.js 18+ | Hosted on Reddit's Devvit platform (no server needed) |

Pick one — they do the same thing.

---

## What It Does

- **`!define <term>`** — Replies to comments with a short Wikipedia summary and a link.
- **Weekly Mod Digest** — Reads a wiki page (`mod-digest`), posts the contents as a stickied mod post every Sunday at midnight UTC, and resets the page for the next week.

---

## File Structure

```
safe-app-llmphysics-bot/
├── bot.py                  # Python entry point. Reddit stream loop.
├── config.py               # Loads env vars, defines constants.
├── plugins/
│   ├── physics_define.py   # Wikipedia lookup logic.
│   └── mod_digest.py       # Weekly mod digest logic.
├── requirements.txt
├── .env.example
├── devvit/                 # Devvit (Reddit-hosted) version
│   ├── devvit.yaml         # Devvit app config
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       └── main.ts         # All bot logic for the Devvit version
└── .gitignore
```

---

## Option A: Python (PRAW) Setup

This runs the bot on your own machine. Works on Linux, macOS, and Windows.

**1. Clone and enter the repo**

```bash
git clone https://github.com/rudi193-cmd/safe-app-llmphysics-bot.git
cd safe-app-llmphysics-bot
```

On **Windows (cmd)**, the commands are the same.

**2. Copy `.env.example` to `.env` and fill in your credentials**

```bash
cp .env.example .env
```

On **Windows (cmd)**, use:

```cmd
copy .env.example .env
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Run the bot**

```bash
python bot.py
```

The bot will stream comments from r/LLMPhysics and respond to `!define` commands. Press Ctrl+C to stop.

---

## Option B: Devvit App Setup

This runs the bot on Reddit's own servers using [Devvit](https://developers.reddit.com/). No server or `.env` file needed — Reddit handles authentication.

**Prerequisites:** [Node.js 18+](https://nodejs.org/) must be installed.

**1. Install the Devvit CLI**

```bash
npm install -g devvit
```

**2. Log in to Devvit**

```bash
devvit login
```

This opens a browser window. Log in with the Reddit account that will own the app. This **must be an account that is a moderator** of the subreddit you want to install the bot on (it needs mod permissions to distinguish and sticky the weekly digest post).

**3. Navigate to the devvit directory**

```bash
cd devvit
```

**4. Create/register the app on Reddit's platform**

If this is your first time setting up the app, you must register it:

```bash
npx devvit init
```

During init, you'll be asked for an app name. A few things to know:

- The name must be **globally unique** across all Devvit apps on Reddit. If `llmphysics-bot` is already taken, pick something else (e.g. `llmphysics-bot-yourname`).
- The name you pick here **does not affect the bot's behavior** — it's just an identifier on the platform. Call it whatever you want.
- `devvit init` will update `devvit.yaml` with the name you choose.
- The app is registered under **whichever account you logged in with** in step 2.

> **This is the step most people miss.** Running `devvit install` or `devvit upload` before `npx devvit init` will give the error: `Error: We couldn't find the app llmphysics-bot. Please run npx devvit init first.`

**5. Install dependencies**

```bash
npm install
```

**6. Test locally (optional)**

```bash
devvit playtest <your-test-subreddit>
```

**7. Upload and install**

```bash
devvit upload
devvit install <your-subreddit>
```

**8. (Optional) Set an app icon**

Save a 256x256 PNG as `devvit/assets/icon.png`, uncomment the `icon:` line in `devvit/devvit.yaml`, then re-run `devvit upload`. See [`devvit/assets/README.md`](devvit/assets/README.md) for details.

---

## Runtime Config (Devvit version)

The Devvit app reads a YAML config from a **mod-only wiki page** on the subreddit it's installed on:

```
https://www.reddit.com/r/<your-sub>/wiki/mod/llmphysics-bot/config
```

Because this page lives under `mod/`, only moderators can edit it. The bot re-reads it at most once every 60 seconds, so edits take effect within about a minute — no `devvit upload` needed.

**What the config controls:**

- **Topic filtering** — `allowed_category_keywords` gates `!define` to Wikipedia pages whose categories contain any of these keywords (e.g. `physics`, `quantum`, `chemistry`). `!define moron` fails the check; `!define quantum entanglement` passes.
- **Blocklist** — `blocked_terms` is a hard refuse list that runs before the category check.
- **Mod digest** — wiki page name, cron schedule, and post title. Changing the cron reschedules the job automatically.
- **Reply wording** — summary length, footer, and all user-facing messages (`not_found_message`, `off_topic_message`, `error_message`). Use `{term}` as a placeholder.

**Setting it up:**

1. Go to `https://www.reddit.com/r/<your-sub>/wiki/create/mod/llmphysics-bot/config`
2. Paste the contents of [`devvit/config.example.yaml`](devvit/config.example.yaml), **wrapped in a fenced code block**, like this:

   <pre>
   ```yaml
   allowed_category_keywords:
     - physics
     - quantum
     ...
   ```
   </pre>

   This is important because Reddit wiki pages render as markdown in the browser, which turns YAML `#` comments into big headers and makes the page unreadable. Wrapping the YAML in a ` ```yaml ` code fence keeps it rendering as a clean monospace block. The bot strips the fence before parsing, so plain (unfenced) YAML also works — the fence is just for human readability.

3. Edit any fields you want to change; leave out anything you want to keep at default.
4. Save. The bot picks up changes within 60 seconds.

If the wiki page doesn't exist or can't be parsed, the bot falls back to the built-in defaults and logs a note — it will not crash.

---

## Environment Variables (Python version only)

| Variable | Required | Description |
|---|---|---|
| `REDDIT_CLIENT_ID` | Yes | Client ID from your Reddit app |
| `REDDIT_CLIENT_SECRET` | Yes | Client secret from your Reddit app |
| `REDDIT_USERNAME` | Yes | Username of the bot account |
| `REDDIT_PASSWORD` | Yes | Password of the bot account |
| `REDDIT_USER_AGENT` | Yes | User agent string (e.g. `llmphysics-bot/0.1 by u/YourBotAccount`) |
| `SUBREDDIT` | No | Subreddit to monitor. Defaults to `LLMPhysics` |
| `MOD_DIGEST_WIKI_PAGE` | No | Wiki page name for digest content. Defaults to `mod-digest` |
| `MOD_DIGEST_FLAIR_TEXT` | No | Flair text for digest posts. Defaults to `Mod Post` |
| `MOD_DIGEST_FLAIR_ID` | No | Flair template ID (optional) |
| `MOD_DIGEST_POST_DAY` | No | Day of week (0=Mon, 6=Sun). Defaults to `6` |
| `MOD_DIGEST_POST_HOUR` | No | UTC hour for the digest post. Defaults to `0` |

### Getting Reddit Credentials

1. Log in as your **dedicated bot account** (a Reddit alt — not your personal account).
2. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).
3. Create a new app. Select **script** as the type.
4. Set the redirect URI to `http://localhost:8080` (unused, but required).
5. Copy the client ID (shown under the app name) and the client secret.

The **Devvit version** does not need these credentials — Reddit handles auth automatically.

---

## Usage

The Devvit bot accepts the `!define` command in two ways:

**1. Prefix mode** — comment starts with `!define`:

> `!define quantum entanglement`

**2. Summon mode** — comment mentions the bot anywhere and contains `!define` anywhere:

> `Hey u/llmphysics-bot, !define quantum entanglement please`

Either way, the bot extracts the term and replies:

> **Quantum entanglement**
>
> Quantum entanglement is a phenomenon where two or more particles become correlated in such a way that the quantum state of each particle cannot be described independently of the others. Measuring one particle instantly influences the state of its entangled partner, regardless of the distance between them. Einstein famously called this "spooky action at a distance."
>
> [Read more](https://en.wikipedia.org/wiki/Quantum_entanglement)
>
> ---
> *I'm a bot for r/LLMPhysics. Use `!define <term>` to look up a physics concept.*

**Why two modes?** Prefix mode is concise. Summon mode lets you write a full comment that mentions the bot without forcing `!define` to be the first word — useful for replies, multi-part messages, and explaining the command in prose without accidentally triggering it (as long as you don't also mention the bot).

**Term extraction:**
- The term is whatever follows `!define` on that line, stopping at the first `.`, `?`, or newline.
- If Wikipedia has no article for the extracted term AND the term is multiple words, the bot falls back to just the first word. So `!define cosmology Do you have any evidence?` still gets a useful reply about cosmology instead of failing silently.

The bot ignores comments that contain `!define` but neither start with it nor mention the bot by username — that's what lets you write _"use the `!define` command"_ in docs without spamming the sub.

---

## Troubleshooting

**Bot doesn't respond to `!define` commands**
- **Python version:** Make sure `python bot.py` is running and the terminal is open. The bot only works while the process is alive.
- **Devvit version:** Make sure you ran all three steps: `npx devvit init`, `devvit upload`, and `devvit install <subreddit-name>`. Just uploading isn't enough — you must install it on the specific subreddit.
- Either start the comment with `!define`, or mention `u/<bot-username>` somewhere in the same comment.
- **Testing on a different subreddit?** For the Python version, set `SUBREDDIT=your_test_sub` in `.env`. For the Devvit version, install the app on the test subreddit with `devvit install your_test_sub`.

**Config changes on the wiki page aren't taking effect**
- Wait up to 60 seconds (the cache) or 5 minutes (the heartbeat sync) — whichever comes first. Posting any `!define` comment will also force an immediate refresh.
- Check the Devvit logs (`devvit logs`) for lines starting with `config loaded from`. They'll show whether the wiki page was read successfully and which values were picked up.

**Cron schedule change didn't fire**
- The bot re-reads the config and reschedules the digest job on a heartbeat every 5 minutes. If you set a cron to fire within that window, the heartbeat may not have run yet. Post a `!define` comment to force an immediate re-sync, then watch the logs for `digest: scheduled with cron "..."`.

**"We couldn't find the app" error**
- Run `npx devvit init` inside the `devvit/` directory before uploading or installing.

**Bot account can't distinguish/sticky posts**
- The bot account (or the Devvit login account) must be a **moderator** of the target subreddit.

---

## Adding Plugins

New commands go in `plugins/` (Python version). Each plugin is a module with its own lookup or handler logic. `bot.py` imports from `plugins/` directly — add a new file, wire it into `handle_comment()` in `bot.py`, and it's live.

For the Devvit version, add new triggers or scheduler jobs directly in `devvit/src/main.ts`.

---

## Dependencies

**Python version:**
- [praw](https://praw.readthedocs.io/) — Reddit API wrapper
- [wikipedia-api](https://wikipedia-api.readthedocs.io/) — Wikipedia article fetching
- [python-dotenv](https://pypi.org/project/python-dotenv/) — `.env` loading
- [APScheduler](https://apscheduler.readthedocs.io/) — Cron scheduling for the weekly digest

**Devvit version:**
- [@devvit/public-api](https://developers.reddit.com/) — Reddit's Devvit SDK
