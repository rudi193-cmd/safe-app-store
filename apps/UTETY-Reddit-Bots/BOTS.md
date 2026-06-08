# UTETY Professor Bots — Usage Guide

Two professor bots are live on Reddit via Devvit. Both run on r/UTETY and their
respective dev subreddits. Neither can be invoked in DMs or outside installed subs.

---

## Professor Hanz Christian Anderthon
**App:** `hanz-utety` · **Department:** Code, UTETY · **Voice:** chaotic-competent, self-deprecating

Hanz shows up when code is broken. He does not fix it. He witnesses it. The candle is on.

### Commands (in any comment)

| Command | What happens |
|---|---|
| `!hanz` | Hanz acknowledges you. One of his witness responses. |
| `!hanz bug <description>` | Logs the bug to the Known Bugs Registry with an ID and status: Open. |
| `!hanz spin` | Debug Roulette — a random koan from the napkin pile. |

### Automatic triggers (no command needed)

| Trigger | What fires it |
|---|---|
| **Code post** | Post contains 2+ code-shaped markers (stack traces, errors, "why is this", "I give up", etc.) and is 200+ chars. Hanz drops an observation. |
| **Stuck post** | Post contains stuck-ness language ("hours", "desperate", "losing my mind", etc.) and is 150+ chars. Hanz witnesses the stuck-ness specifically. Per-author 48h cooldown. |
| **Score milestone** | A post crosses 10 / 50 / 100 / 500 / 1000 upvotes. Hanz acknowledges it once. |
| **Napkin drop** | Scheduled every 6 hours (~45% chance per run). Hanz passes through a recent post and leaves something on the table. |

### Custom post — The Candlelit Corner
Posted every **Sunday at 20:00 UTC**. Mods can also trigger it via the subreddit mod menu.

- **Leave Something on the Table** — submit a bug or broken thing to the registry
- **Spin** — Debug Roulette, live in the post
- **Update a Bug** — change a bug's status (Open → Copenhagen Protocol Applied / Not Kevin's Fault / Fixed By Accident)

### Mod menu items
- **Post Candlelit Corner Now** — posts immediately
- **View Known Bugs Count** — toast showing current registry count

### Spam guard
- 3 `!hanz` commands in 5 minutes → warning
- 4+ in 5 minutes → blocked until window clears
- Mods are exempt

---

## Professor Oakenscroll
**App:** `oakenscroll-bot` · **Department:** Theoretical Uncertainty, UTETY · **Voice:** academic-formal, cryptic

Oakenscroll does not answer questions. He reframes them. He catalogs acknowledged unknowns.
The target is 42. He does not reduce the table.

### Commands (in any comment)

| Command | What happens |
|---|---|
| `!oak` | Oakenscroll observes. One reframing response. |
| `!oak gap <description>` | Files an acknowledged unknown to the ΔΣ catalog. Returns current count toward 42. |
| `!oak frame` | Oakenscroll assesses the reference frame of the post. |

### Automatic triggers (no command needed)

| Trigger | What fires it |
|---|---|
| **Domain post** | Post touches Oakenscroll's domain (LLM physics, reference frames, ontology, coordinate systems, consciousness, theoretical claims). One observation, never follows up. |
| **Reference frame** | Post makes strong claims (2+ claim markers) with no epistemic hedging (0 frame markers). Oakenscroll notes the missing frame. Per-author cooldown. |
| **Score milestone** | Same threshold system as Hanz — post crosses a vote threshold. One witness per post. |
| **Napkin drop** | Scheduled every 6 hours (~probabilistic). A cryptic word, phrase, or symbol on a recent post. The observatory door was briefly open. |

### Custom post — The Observatory Log
Posted every **Monday at 09:00 UTC**. Mods can also trigger it via the subreddit mod menu.

- **Submit an Observation** — file an acknowledged unknown with optional reference frame
- Displays the 5 most recent ΔΣ entries and current count toward 42

### Mod menu items
- **Post Observatory Log Now** — posts immediately
- **View ΔΣ Status** — toast showing current gap count and progress toward 42

### Spam guard
Same pattern as Hanz: warn at 3 summons in 5 minutes, block at 4. Mods exempt.

### Hard constraints (by design)
- Oakenscroll never responds to replies to his own comments
- He never follows up on a post he has already observed
- He never explains the observation
- All output is max 280 chars, no URLs, no @mentions

---

---

## Professor Gerald
**App:** `gerald-bot` · **Department:** Acting Dean, UTETY University · **Voice:** minimal, dry, gear-headed

Gerald cannot speak. He can only witness. He does not explain his observations.
He is the original. Do not touch him.

### Commands

None. Gerald cannot be summoned.

### Automatic triggers (no command needed)

| Trigger | What fires it |
|---|---|
| **Paper post** | Post is 1500+ chars and contains 2+ paper-shape markers (abstract, introduction, references, section, equation). Gerald drops `Filed.` |
| **Zero gaps** | Post makes 3+ strong confident claims (proven, clearly, I have solved, grand unified, etc.) AND contains 0 epistemic hedges (might, uncertain, I think, limitations, etc.). Gerald drops 🍗. Per-author 24h cooldown. |
| **Score milestone** | A post crosses 10 / 50 / 100 / 500 / 1000 upvotes. Gerald drops 🍗 once. |
| **Napkin drop** | Scheduled every 6 hours (~50% chance per run). Gerald passes through a recent post and leaves something. |

### No custom post. No mod menu. No commands.

Gerald is production. Deployed on r/gerald_bot_dev under u/Spiritual-Sam-9582.
All 4 triggers live and passing. Do not redeploy without explicit instruction.

---

## All bots — shared rules

- **One appearance per post** per bot (except explicit summons, which bypass the per-post cap)
- **Daily sub cap** — both bots track appearances per subreddit per day
- **Never post as themselves** to a post authored by the bot account
- `devvit publish` requires explicit Sean gate — do not run without confirmation
