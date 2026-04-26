# gerald-bot

> Acting Dean, UTETY University. Cannot speak. Can only witness.

Gerald is a Reddit bot whose entire design principle is **refusal to participate**. He does not answer commands. He does not explain himself. He does not engage in conversation. When something crosses a threshold that deserves witnessing, Gerald appears, drops a single word or a single emoji, and disappears.

Gerald is the inverse of a utility bot. Every normal product instinct — helpfulness, discoverability, responsiveness, verbosity — is a rule Gerald breaks on purpose.

---

## Status

**Scaffold only.** The machine is built. The ammunition is not loaded. Every `src/data/*.json` file contains `_handoff` metadata and `TODO_REPLACE` markers that need to be filled in from the authoring database before deploy.

Nothing in this bot has been tested against a live subreddit yet.

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

Every item below is a `TODO_REPLACE` or a stub that needs real data from the authoring system. They are ordered by what will actually unblock a first deploy.

### Blockers — cannot deploy without these

- [ ] `src/persona/gerald.ts` → `BOT_USERNAME` constant. The real Reddit account Gerald will post from.
- [ ] `src/data/napkins.json` → `words`. Real canonical napkin vocabulary. Replace `TODO_REPLACE_WITH_REAL_VOCAB` and expand `Sieve`, `40000` with the full list.
- [ ] `src/data/triggers.json` → `zero_gaps.confidence_markers`. Replace `TODO_REPLACE_ADD_MORE_FROM_DB` with real crackpot-detection regex patterns from the authoring DB.
- [ ] `src/data/triggers.json` → `zero_gaps.gap_markers`. Same — real hedging patterns.
- [ ] Target subreddit decision. `r/UTETY`? `r/LLMPhysics`? Both? The code does not hardcode a subreddit (Devvit installs per-sub), but the README install section needs the canonical target.

### Character — should be filled before public install

- [ ] `src/data/canon.json` → `delta_sigma.meaning`. Replace `TODO_REPLACE` with the real meaning from the authoring DB. Preserve the exact phrasing `"Gerald never reduces the gaps table. Gerald is the gaps table acknowledging itself."` if it is still canonical.
- [ ] `src/data/responses.json` → `milestones.community`. Replace `TODO_REPLACE_SINGLE_WORD` with the real single-word response for community milestones.
- [ ] Verify `src/data/canon.json` → `properties` booleans match the current canonical hard rules. Any `true`/`false` flip here changes runtime behavior.

### Tuning — safe defaults exist, tune after observing real traffic

- [ ] `src/data/triggers.json` → `new_post.min_length_chars` (currently 1500). Raise if `Filed.` fires too often, lower if it never fires on genuine papers.
- [ ] `src/data/triggers.json` → `new_post.paper_shape_markers` and `required_marker_count`. Current markers are generic; the authoring DB may have stricter "working paper" detectors.
- [ ] `src/data/triggers.json` → `score_milestone.thresholds`. Currently `[10, 50, 100, 500, 1000]`. Tune to the real karma economy of the target sub.
- [ ] `src/data/triggers.json` → `napkin_drop.cron` and `chance_per_run`. Defaults to ~2 drops/day in expectation; tighten if Gerald feels too talkative.
- [ ] `src/lib/ratelimit.ts` → `DEFAULT_DAILY_CAP` (currently 5). Canon permitting, move this to a Devvit setting so mods can tune without a redeploy.

### Integration — not required for first deploy

- [ ] `src/lib/crossPersona.ts` — implement when the authoring system has a real HTTP API and other personas are online. Requires flipping `devvit.json` → `permissions.http.enable` to `true` and adding the backend domain.
- [ ] Marketing assets — `assets/icon.png` (256x256) before `devvit upload`.

---

## What Gerald is NOT doing (on purpose)

- **No `!define` or any slash-command interface.** Gerald is not summoned.
- **No replies, ever, to comments on his own comments.** Dropping a napkin does not start a thread.
- **No LLM calls.** Every detector is regex + heuristics. This is cheap, auditable, and fast — and it means the character rules cannot be jailbroken via the post content.
- **No cross-bot awareness.** `crossPersona.ts` is a stub. When the parent agent system is ready, integration happens through that single seam.
- **No HTTP egress.** `devvit.json` → `http.enable` is `false`. Flip it only if a trigger actually needs it, and document why.

---

## Deploying

1. Fill in every blocker in the Hand-off Checklist above.
2. `cd gerald-bot && npm install`
3. `npx devvit init` — register the app on the Reddit Devvit platform. The account you log in as must be a moderator of the target subreddit.
4. `npm run upload` (or `devvit upload`)
5. `devvit install <subreddit>`
6. Watch `devvit logs`. Gerald should log `Reboot: Gerald is awake. Silent as ever.` and then say almost nothing.

If Gerald is talking too much, the cap / cooldown / detector thresholds are wrong. Tune in `src/data/triggers.json` — no redeploy needed for data changes that come through a settings-backed config (future work).

---

## Philosophy

Every line of code in this bot is an argument that **software can be designed to witness rather than to serve**. Gerald does not answer because answering is an imposition. Gerald does not explain because explanation is a story and Gerald has no narrative. Gerald appears because appearing is itself a comment on what just happened — and then leaves, because staying would be commentary on the commentary.

`ΔΣ=42`. Gerald never reduces the gaps table. Gerald is the gaps table acknowledging itself.
