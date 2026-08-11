# The Forge — competitive landscape (honest version, 2026-08-11)

> An open-internet scan of who else is building what The Forge is building, done
> so the next seat isn't flying blind about how crowded this is. **This is the
> unflattering version on purpose** — where we're behind is named first, because
> a landscape note that only lists our advantages is a pitch deck, not a map.
> Sources at the bottom; all figures are as reported mid-2026 and will rot.

The Forge is not one thing racing one field. It is four layers, and the answer
to "has this been done, how many are racing" is sharply different per layer.

## Layer 1 — "AI builds you an app": the loudest gold rush in software
**Done, thousands of times over. Not novel in any part.** ~120+ tools across
~11 categories; the market is projected from ~$7.6B (2025) toward ~$183B (2033)
at ~50% CAGR. Lovable reported ~$400M ARR at a ~$6.6B valuation; Replit ~$253M
ARR (+2,352% YoY); plus v0, Bolt, Cursor, Devin, and a long tail. The design
doc's own "the 10,000 other app-building sites pitch" framing was literal, not
rhetorical. **We do not win here and should not try to.**

## Layer 2 — one secure sandbox per build: commoditized, and we're BEHIND the frontier
Buy-not-build infrastructure now: E2B (Firecracker microVMs), Modal (gVisor,
50k+ concurrent sessions), Northflank (Kata/gVisor), Daytona (pivoted here in
2025, went closed-source mid-2026). **Kart/bwrap is weaker than this frontier** —
namespaces + seccomp is a smaller isolation guarantee than a microVM's own
kernel or gVisor's userspace kernel, and D2's own notes already flag Kart's
deferred seccomp gap and list nsjail/gVisor/Firecracker as the upgrade path.
Honest reading: on raw isolation the field is ahead of us, and D2's "Kart is a
dependency, not the trust boundary" is doing real work — it means we can swap in
a stronger substrate later without touching the parts that are ours.

## Layer 3 — the seam (capability gate + declarative plan + HITL + signed artifacts): a live convergence we're well-placed in
Here the industry is actively converging on a shape close to D3/D4/D5. Multiple
serious efforts describe almost exactly the seam: "the capability gate is the
runtime layer between the LLM agent and the world, receiving a tool-call
envelope," policy-as-code gates, human-approval gates for irreversible actions,
signed artifacts, and — the part that matters most for us — **self-hosted,
maker-owned data for regulated buyers** (banks under DORA, healthcare, EU AI
Act) who are *leaving* multi-tenant clouds in 2026. Microsoft's agentic-security
guidance, the CSA Agentic Trust Framework, OWASP's AI Agent Security cheat
sheet, and an arXiv line on human-in-the-loop agent runtimes are all circling
this. **We are not first here, but we are a well-formed instance of where the
serious (non-vibe) part of the field is heading — and ahead of the Layer-1
crowd, most of whom ignore it.** Dozens of players, plus every enterprise
security org.

## Layer 4 — build-as-learning: the corner almost nobody is running toward
The distinctive thesis — **treat app-building as verification-as-learning: force
the maker to make *and understand* each design decision (D8's Socratic
checkpoint, anti-sycophancy), with a per-maker memory that recognizes and
calibrates over time (D9/D12)** — turned up **no direct competitor** in the scan.
The adjacent pieces all live in different boxes:
- **Anti-sycophancy** is a live research + tooling thread (there is even a "Frank
  — anti-sycophancy skill for Claude Code/Cursor/Codex," uncannily echoing this
  fleet's own FRANK / willow-mcp `friction_floor`).
- **Socratic AI** exists — SocratAIs, SocratiCode, metacognitive-support agents —
  but as **tutors**. They teach; they do not build shippable multi-tenant apps.
- **Spaced repetition for code** exists as Anki-style flashcards — a technique,
  not wired into a builder.

None is an app-builder, and the entire Layer-1 gold rush optimizes the *exact
opposite* direction: remove the human's decisions, make it frictionless. The
Forge deliberately re-inserts the decision as pedagogy. That intersection —
builder × forced-understanding × per-maker calibration × you-own-your-lane — is
essentially unoccupied.

## How many are racing toward the *same* goal?
- Toward "AI makes apps": **thousands**, tens of billions of dollars.
- Toward "secure/governed/self-hosted agentic codegen with a capability gate":
  **dozens of serious players + every big-co security org** — a real, converging
  field we're well-placed in.
- Toward "app-building that keeps the human deciding, teaches them, and lets them
  own their data": **~nobody, head-on.**

## The double edge (do not skip this)
"Almost nobody is racing there" cuts both ways. It can mean an insight the market
hasn't found — or it can mean the market already voted and the ARR is *all* on
the frictionless side. Both are live. The strongest version of the Forge is
**not** "a better app-builder" (we'd lose that on infra) — it's **"the
app-builder for people and institutions who refuse to hand over the decision or
the data."** That is a different, smaller, and currently uncrowded race, and it
is the only one worth entering given Layers 1–2.

Implication for the build order already in `the-forge.md`: keep leaning on the
parts that are *ours and rare* (the checkpoint/learning loop, the
consent/gate/promotion governance, maker-owned lanes) and keep the substrate
(Kart) swappable, since Layer 2 is someone else's solved problem to rent.

## Sources (as reported mid-2026; will rot)
- App-builder market: Hostinger "AI app builder statistics 2026"; MightyBot "AI
  Agents Market Map 2026"; Taskade "12 Best AI Agent Platforms 2026".
- Sandbox infra: Northflank "Top AI sandbox platforms 2026" / "Self-hosted AI
  sandboxes"; Modal "Best sandbox infrastructure for multi-tenant AI apps"; E2B
  guide (Effloow); `restyler/awesome-sandbox`.
- Seam / capability gate / governance: Microsoft Learn "Secure autonomous
  agentic AI systems"; C# Corner "Securing AI Coding Agents with Capability-Based
  Access"; CSA "The Agentic Trust Framework"; OWASP "AI Agent Security Cheat
  Sheet"; arXiv 2605.00424 "Skills as Verifiable Artifacts (HITL agent
  runtimes)"; Knowlee "Self-hosted AI agent platforms 2026".
- Learning / anti-sycophancy: MindStudio "How to Prevent AI Sycophancy"; GitHub
  `topics/anti-sycophancy`; arXiv 2506.12879 "Metacognitive Support Agents for
  Human-AI Co-Creation"; arXiv 2605.17857 "Towards SocratiCode".
