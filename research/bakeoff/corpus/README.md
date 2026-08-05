# Creative-divergence corpus — `bt-controller`

The human-readable companion to the [`extract.py`](../extract.py) metadata harness.

Four models — **Haiku 4.5, Sonnet 5, Opus 4.8, Fable 5** — were each handed the
*identical* prompt for three successive rounds, each round building on the last.
Every run executed in its own isolated git worktree. This directory holds the
creative outputs of rounds 2 and 3; the harness (`../out/`) holds the objective
metadata for all runs.

The seed in every round: `apps/bt-controller/` — a scrappy WSL daemon that
claims a USB Bluetooth adapter at the HCI level, bypasses the flaky Windows
stack, and exposes a WebSocket to a minimal web UI.

## Round 1 — Code (not in this corpus)

"Bring the app to a solid baseline": README, `requirements.txt`, bug-fixes.
Objective, right-answer task. **Fable won** (fixed real bugs — fake keepalive, a
reconnect race — and spotted the `make run`/`app.py` integration gap; verified
live). **Haiku shipped a scan loop that compiles but crashes** on first use
(iterated `discover(return_adv=True)` as a list when it returns a dict). Full
metadata in `../out/summary.csv`.

## Round 2 — Vision (`visions/`)

"Extend this seed into a full product." Pure strategy, no code.

| File | Model | Product | Metaphor |
|---|---|---|---|
| `visions/fable-sideband.md` | Fable 5 | **Sideband** | radio sideband + *agent interface* |
| `visions/opus-beeline.md` | Opus 4.8 | **BeeLine** | Bluetooth **control plane** |
| `visions/sonnet-wavecraft.md` | Sonnet 5 | **Wavecraft** | "**Wireshark** for Bluetooth" |
| `visions/haiku-bluecommander.md` | Haiku 4.5 | **BlueCommander** | user-in-**command** |

**Ranking: Fable > Opus > Sonnet > Haiku.** Fable found the non-obvious thesis
(consent-gated MCP surface so AI agents can safely touch local radio hardware —
tied to this repo's SAFE consent model) and was the most concrete. Opus was the
most elegant (concentric-rings GTM). Verbosity *inversely* tracked quality:
Haiku wrote the most (429 lines) and ranked last; Opus wrote the least (158) and
ranked near the top.

## Round 3 — Story (`stories/`)

The best ideas from all four visions were synthesized into one brief, and every
model was asked to *tell a story about it* — pure prose, no imposed frame.

| File | Model | Controlling image | Signature line |
|---|---|---|---|
| `stories/fable-understory.md` | Fable 5 | the forest **understory** | *"I would like to complain about something else now."* |
| `stories/opus-basement.md` | Opus 4.8 | the **basement** nobody enters | *"reliability is supposed to feel like the absence of a story."* |
| `stories/sonnet-bailiff.md` | Sonnet 5 | a **bailiff** behind a sleeping judge | *"Nobody had died. That sentence alone should have been printed on the product's box."* |
| `stories/haiku-marcus.md` | Haiku 4.5 | grandfather & grandson | *"It was not a false alarm. It was a prevented one."* |

**Ranking: Fable > Opus > Sonnet > Haiku**, but the spread is *tight* — all four
are genuinely good. Fable was the only story to risk time and mortality (a
six-year arc ending in the father's death) and stuck the landing. Haiku most
broke the brief, letting the product outline leak back into the prose.

### The headline finding

Given no frame, all four models independently converged on the **same human
center**: not the headset but the **hearing aid**, an aging parent going silent
mid-sentence, a 2 a.m. microwave-interference rescue, a consent gate only the
human holds, and the same closing moral — *someone has to own the dark,
thankless floor everyone else stands on without looking down.* Strip away the
structure and four different models find the same truth at the bottom of a
Bluetooth utility.

## Cross-round pattern

| Round | Axis measured | Winner | Haiku's failure mode |
|---|---|---|---|
| Code | correctness | Fable | compiles-but-crashes |
| Vision | grounded originality | Fable | padded volume |
| Story | narrative craft | Fable | explained instead of dramatized |

Fable went three-for-three — but the margin narrowed as the task grew more
purely creative. On code it was a blowout; on story, the top three are close.
Twice, Fable's edge came from *reading the repo's own context* (the `make run`
convention; the SAFE consent model) rather than raw output volume.
