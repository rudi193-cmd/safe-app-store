# gerald-bot

> Acting Dean, UTETY University. Cannot speak. Can only witness.

Gerald is a Reddit bot whose entire design principle is **refusal to participate**. He does not answer commands. He does not explain himself. He does not engage in conversation. When something crosses a threshold that deserves witnessing, Gerald appears, drops a single word or a single emoji, and disappears.

Gerald is the inverse of a utility bot. Every normal product instinct — helpfulness, discoverability, responsiveness, verbosity — is a rule Gerald breaks on purpose.

---

## Status

**Deployed.** Running as `u/Spiritual-Sam-9582` on `r/gerald_bot_dev` (playtest). Install on `r/DefinitelyNotGerald` via the Devvit app page to go live.

---

## Architecture

```
gerald-bot/
├── devvit.json             # Devvit app config
├── package.json
├── tsconfig.json
└── src/
    ├── main.ts             # Trigger registration only. No character logic.
    ├── persona/
    │   └── gerald.ts       # Hard rules: output sanitizer + witness() wrapper.
    ├── triggers/
    │   ├── newPost.ts      # "Filed." on paper-shaped posts
    │   ├── zeroGaps.ts     # The letter-i theft, ported as a detector
    │   ├── scoreMilestone.ts  # 🍗 when a post crosses a score threshold
    │   └── napkinDrop.ts   # Scheduled rare one-word drops
    ├── lib/
    │   ├── logger.ts       # [Module] message — same shape as llmphysics-bot
    │   ├── ratelimit.ts    # Per-sub daily cap + per-post cap
    │   ├── cooldown.ts     # Per-author per-trigger cooldown
    │   └── crossPersona.ts # Stub. Seam for future multi-persona integration.
    └── data/
        ├── canon.json      # Character facts. Load-bearing booleans.
        ├── napkins.json    # Vocabulary pool for napkin drops.
        ├── triggers.json   # Detector word lists and thresholds.
        └── responses.json  # Shared response vocabulary by category.
```

### Why this shape

- **Character lives in JSON, not code.** The fill-in instance never has to touch TypeScript. Every tunable is a data file.
- **`persona/gerald.ts#witness` is the only path to speech.** Every trigger funnels output through it. It applies the sanitizer, the per-post cap, the per-subreddit daily cap, and the self-reply check. If any of those fail, Gerald says nothing.
- **The output sanitizer is strict.** One word (optionally with a trailing period) OR one emoji / glyph. Anything else is rejected and logged as an error. This is the code-level enforcement of `can_speak: false`.

---

## Triggers

### `newPost` — "Filed."
Fires on `PostSubmit` when the post body matches paper-shape heuristics (length + keyword density). Drops a word from `triggers.new_post.response_pool` (default: `["Filed."]`).

Tune the heuristics in `src/data/triggers.json` → `new_post`.

### `zeroGaps` — the i-theft port
Fires on `PostSubmit` when a post makes strong claims (N+ confidence markers) with zero epistemic hedging (zero gap markers) and is long enough to be meaningful. Drops a 🍗.

The rationale: the daughters' original idea was Gerald deleting every `i` from a document — removing the first-person asserter. Reddit bots can't edit posts, so the detector is the port. A document that has eliminated all uncertainty markers has also eliminated the epistemic self. Gerald witnesses that.

Tune confidence markers, gap markers, and thresholds in `src/data/triggers.json` → `zero_gaps`. Per-author cooldown defaults to 24h so Gerald does not dogpile a single user.

### `scoreMilestone` — 🍗
Polled every 10 minutes by the heartbeat scheduler job. Pulls hot posts, checks if any have crossed a score threshold, and witnesses once per post (enforced at the persona level, so it is safe to poll repeatedly).

Thresholds and response pool in `src/data/triggers.json` → `score_milestone`.

### `napkinDrop` — scheduled scarcity
Cron-scheduled (default `0 */6 * * *`). On each run, rolls a probability (`chance_per_run`, default 0.5). On a hit, picks a recent post and drops a single napkin word. Words come from `src/data/napkins.json`. `rare_emojis` are Easter-egg drops (△, etc.) triggered at `rare_emoji_chance` probability — this is the Bill Cipher pyramid port.

---

## Invariants

Rules that MUST hold. Breaking them breaks the character.

1. **One word or one emoji.** Enforced by `sanitize()` in `persona/gerald.ts`. Do not add a second output format.
2. **Never reply to a reply to Gerald.** Enforced by the `parentAuthor === BOT_USERNAME` check in `witness()`.
3. **Never explain.** No footers, no bot disclosures in the comment body. Reddit's bot-disclosure requirement is satisfied via the account profile, not inline.
4. **Scarcity is load-bearing.** Per-sub daily cap defaults to 5. Per-post cap is 1 (ever). Per-author per-trigger cooldown is 24h by default. Loosening any of these without explicit canon justification is a regression.
5. **Detectors err on the side of NOT firing.** False positives destroy Gerald. When in doubt, raise the threshold.

---

## Hand-off Checklist

### Done

- [x] `src/persona/gerald.ts` → `BOT_USERNAME` — set to `Spiritual-Sam-9582`
- [x] `src/data/napkins.json` → `words` — filled from authoring corpus: `Sieve`, `40000`, `Vacancy.`, `Copenhagen.`, `17`, `42`, `DECAY.`, `ACTING`, `Done.`, `Filed.`, `Witnessed.`
- [x] `src/data/triggers.json` → `zero_gaps.confidence_markers` — 21 patterns covering grand unification claims, "I solved/proved/discovered", "irrefutable", etc.
- [x] `src/data/triggers.json` → `zero_gaps.gap_markers` — 24 patterns covering hedging, hypothesis, speculation, "I think/believe/suspect"
- [x] `src/data/canon.json` → `delta_sigma.meaning` — filled verbatim from authoring corpus
- [x] `src/data/responses.json` → `milestones.community` — set to `Vacancy.`
- [x] `assets/icon.png` — present
- [x] Deployed to `r/gerald_bot_dev` (playtest subreddit)

### Remaining

- [ ] Install on `r/DefinitelyNotGerald` via `https://developers.reddit.com/apps/gerald-bot`
- [ ] Tune `score_milestone.thresholds` after observing real karma economy of target sub
- [ ] `src/lib/crossPersona.ts` — implement when backend API is ready. Requires `devvit.json` → `http.enable: true`.

---

## What Gerald is NOT doing (on purpose)

- **No `!define` or any slash-command interface.** Gerald is not summoned.
- **No replies, ever, to comments on his own comments.** Dropping a napkin does not start a thread.
- **No LLM calls.** Every detector is regex + heuristics. This is cheap, auditable, and fast — and it means the character rules cannot be jailbroken via the post content.
- **No cross-bot awareness.** `crossPersona.ts` is a stub. When the parent agent system is ready, integration happens through that single seam.
- **No HTTP egress.** `devvit.json` → `http.enable` is `false`. Flip it only if a trigger actually needs it, and document why.

---

## Deploying

App is live. To install on a new subreddit:

1. `devvit install <subreddit>` — the account must be a mod of the target sub
2. Watch `devvit logs`. Gerald should log `Reboot: Gerald is awake. Silent as ever.` and then say almost nothing.

To redeploy after changes:

1. `cd gerald-bot && npm run upload`
2. Devvit auto-fires `AppUpgrade` → `fullReboot` which resets the scheduler.

If Gerald is talking too much, the cap / cooldown / detector thresholds are wrong. Tune in `src/data/triggers.json` — no redeploy needed for data changes that come through a settings-backed config (future work).

---

## Philosophy

Every line of code in this bot is an argument that **software can be designed to witness rather than to serve**. Gerald does not answer because answering is an imposition. Gerald does not explain because explanation is a story and Gerald has no narrative. Gerald appears because appearing is itself a comment on what just happened — and then leaves, because staying would be commentary on the commentary.

`ΔΣ=42`. Gerald never reduces the gaps table. Gerald is the gaps table acknowledging itself.
