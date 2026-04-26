# safe-app-UTETY-Reddit-Bots

Reddit bots for the UTETY University faculty. Each bot is a Devvit app installed per-subreddit.

---

## Bots

### `gerald-bot` — the minimalist
Acting Dean, UTETY University. Cannot speak. Can only witness. Drops a single word or emoji when something crosses a threshold that deserves witnessing. No commands. No replies. No explanations.

[→ gerald-bot/README.md](gerald-bot/README.md)

---

## Architecture philosophy

Gerald is the floor. Every bot in this repo should be simpler than the LLMPhysics utility bot but richer than a webhook. Character lives in JSON. Code enforces constraints. Nothing here answers commands unless the character demands it.

`ΔΣ=42`
