# Detonation lane: observed egress as a second measured fact

**Sean Campbell** · Proposal · August 2026

> Status: **proposed** (no implementation). Lane 1 targets the Waydroid
> container [`playgate`](../../apps/playgate) already requires.
>
> **Landing note.** Parked here at the operator's direction, knowingly against
> the instruction in the banner below, because the SOIL route was not available:
> the Grove connector was unauthenticated in the session that landed this and
> the OAuth flow cannot be run non-interactively. This is a holding location,
> not a home.
>
> **The banner below still governs.** On transcription into `gate_app_ideas`,
> delete this file rather than leaving it as a second copy — and until then,
> edit it here rather than anywhere else, because the playground branch it came
> from is being pruned.

> **Destined for SOIL, not for prose.** This file exists because `willow-mcp`
> was not connected to the session it was written in, so it could not be parked
> in `gate_app_ideas` directly. Transcribe it and delete this copy — a proposal
> living in two places is a proposal that gets edited in the wrong one.
>
> | Field | Value |
> | --- | --- |
> | collection | `gate_app_ideas` |
> | app id | `gate_scratch` |
> | scope | `gate_*` |
> | id | `gate_detonation_lane` |
> | status | `proposed` |
> | confidence | `medium` — the Android lane is well understood; the generalisation past it is not |
>
> `status` and `confidence` values above are guesses at the collection's
> vocabulary. Correct them on transcription rather than importing them as-is.

---

## The idea, once, plainly

Run a package in a sandbox on your own machine, watch what it reaches for, and
write down what you saw. Which hosts it resolved. Which declared permissions it
actually exercised. What it wrote, and where. Emit a plain readable transcript.

Nothing is uploaded. The file never leaves the machine it is being tested on.

## What this is not

**It is not the interruption count**, and the schema must not let it become the
interruption count.

A detonation produces *observed egress*: "resolved seven ad domains in ninety
seconds." The interruption record holds *observed interruption*: "stopped the
child six times in ten minutes." These correlate. They are not the same fact,
and one is much cheaper to collect than the other.

That asymmetry is exactly the failure mode the paper this came out of is about.
A cheap proxy, sitting next to an expensive fact, in a field that will accept
either, gets used for both — and then a catalog entry says `measured` while
nobody has watched a child play anything.

So: a separate field, its own provenance state, and `min()` across both.

```
egress:        measured    (detonated 2026-08-02, 90s, transcript attached)
interruption:  assumed     (nobody has watched this run)
confidence:    assumed
```

That row is coherent and it is honest. A scoring system would have averaged it
into something that looked like progress.

## Why this is worth building rather than adopting

Detonation sandboxes exist — Cuckoo, the commercial analysis suites, the
behavioural tab on the large scanning services. Nearly all of them work the
same way: **you upload the file to somebody else's infrastructure.**

The tool that tells you what a file leaks operates by making you leak it first.

For a corporate malware team that is a reasonable trade — the file is already
hostile and already theirs. For a parent checking a children's game, or anyone
checking a document they are not permitted to send anywhere, it is the
account-server-subscription wall again in a lab coat. Same move, one layer up
from the products already scored in the sovereignty report: the measurement of
the risk is available only by accepting the risk.

A local-first detonation harness is underserved for exactly the reason
everything else in this lane is underserved. Nobody sells it because there is no
subscription in it.

## What is genuinely hard

Stated up front so the first clean run does not get over-read.

**Coverage.** You observe only what you triggered. An app that phones home on
day three, or after a level-up, or only on a cellular connection, shows nothing
in a ninety-second run. This is not solvable, only *stated*: a clean detonation
means "nothing observed in this run," never "nothing there." The transcript must
carry its own duration and what was exercised, or it will be read as the
stronger claim.

**Evasion.** Anything that checks whether it is running in an emulator behaves
differently when it is. Adaptive ad scheduling is the mild version; deliberate
sandbox detection is the aggressive one. A quiet run in a sandbox is weaker
evidence than a quiet run on real hardware, and the record should say which it
was.

**Isolation is the entire engineering cost.** A sandbox that leaks is worse than
no sandbox, because it produces confident clean transcripts while being the
vector. This is the reason the staging below starts where it does.

## Staging

**Lane 1 — Android, on infrastructure already standing up.** Playgate already
requires Waydroid. Install into it, run for a fixed window, and capture three
streams: `adb logcat`, DNS resolution, and a packet capture on the bridge
interface. Emit resolved hosts, exercised permissions, and the run's duration.

This is a weekend rather than a year because there is no new isolation story to
get right — the container already exists for another reason, and the failure
mode of a leaky Waydroid is bounded by what Playgate was already willing to
install.

**Lane 2 — decide only after lane 1 has run end to end on a real APK.** The
obvious next targets are documents and arbitrary binaries, and both need an
isolation story that Waydroid does not provide. Do not start them early. The
value of lane 1 is not the Android results; it is finding out what the
transcript format needs to say before there are three formats to reconcile.

## Gates

A detonation harness with no gate is a script that produces reassuring output.

- **A run with zero observed egress must be distinguishable from a run that
  failed to capture.** Point the harness at a package known to call out, assert
  it is seen. Break the capture on purpose and assert the run reports *failed*,
  not *clean*. This is the single most important test in the project: silent
  capture failure reads as a perfect result.
- **The transcript must carry its own limits** — duration, what was exercised,
  sandbox versus hardware — as fields, not prose. A consumer that reads only the
  host list will otherwise treat ninety seconds as forever.
- **`egress` must not be writable from static analysis.** If a code path can set
  it from an SDK inventory, the field has silently become `fitted` while
  claiming `measured`.

## Open questions

1. **Does a sandbox run ever justify `measured`, or only ever `fitted`?** The
   evasion problem is a real argument that detonation is inherently derived —
   you measured the sandbox's experience, not the child's. A defensible position
   is that `measured` requires hardware, and every sandbox run caps at `fitted`
   however good the capture was. That is stricter than it needs to be and it
   might be right.
2. **How long is a run?** Ninety seconds is a guess. Whatever it is, it goes in
   the transcript.
3. **Does this stay inside Playgate or become its own thing?** It is useful
   independently, which is usually the signal for a separate repo — but the path
   out runs through a compliant repo, not straight to promotion, and lane 1 has
   not run yet.

## Provenance of this document

Every claim here about existing tools is `assumed` — written from working
knowledge, in a session whose egress policy permitted GitHub and nothing else,
so nothing was checked against a primary source. Before any of this is quoted,
confirm: which sandboxes actually require upload versus offering a local
deployment, and what Waydroid's bridge interface exposes to a capture. Both are
load-bearing and neither was verified.
