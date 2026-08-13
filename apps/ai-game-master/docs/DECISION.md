# Decision — what an AI Game Master is, and what it reuses vs. builds

*Status: proposed. This doc records reasoning and closed doors; it seals
nothing. A machine answer stands as a draft until a named human seals it — this
document included.*

*Provenance: drawn from a real playthrough. The Vander valley campaign was run
for a room of eight-to-ten-year-olds, once a week for ~seven months, and then
dogfooded through Nestor's hash-chained ledger as the game's book of record (the
run log and lore bible live in the private box, `sean-data-vault`). Every claim
below traces to that run or to an organ already in the fleet.*

---

## 0. The one-sentence thesis

**An AI Game Master is a yes-and bookkeeper, not a rules referee.** It proposes,
rolls, and remembers; a named human at the head of the table seals canon. The
moat is memory, continuity, and sealed-canon authority — not rules rigor.

## 1. The decision to make

Do we **build** an AI-GM from scratch, or **reuse** what exists and **inject**
what the fleet already holds? The answer decides where every hour of effort goes.

**Decision: reuse the game-engine plumbing, inject the fleet's organs, build
only the seam that joins them.** Concretely:

| Tier | What | Where it comes from |
|---|---|---|
| **REUSE** (open shelf) | rules text, dice, tables | SRD 5.1 / 5.2 (CC-BY 4.0); an MIT dice roller. Plumbing, not a moat. |
| **INJECT** (the fleet) | tamper-evident ledger, human-seals-canon, entity resolution, signed rulings, a corpus search seam | Nestor, terpsi-music, Jeles — **already built and pointed outward.** |
| **BUILD** (the seam) | the GM loop that proposes/rolls/remembers and routes every "is this true now?" through a human seal | this repo's schemas + the engine that runs on them. |

**Reason.** The plot is the cheap part — a machine renders the whole Vander
mechanical spine in seconds (the dogfood sims ran in well under a second each).
The expensive, valuable part is the seven months at the table. So spend nothing
rebuilding rules engines that already exist, and spend everything on the seam
that lets a machine carry the *toil* while the human keeps the *magic*.

## 2. The differentiator (why this is not another AI-DM tool)

Every AI-DM tool on the shelf optimizes for **rules rigor** — adjudicate the
grapple, resolve the opportunity attack. That is precisely what LLMs are **worst**
at and what a rules engine already does for free.

The Vander table did the opposite and it *worked*: the DM **loosened the dice**,
let **role-play count for more than the mechanics allowed**, and said **yes-and**
when the kids walked in **Beetlejuice, the Sandworm, and Bill Cipher.** That
plays *to* the model's strengths (improv, narrative, holding incomplete
information) and away from its weaknesses (rigid adjudication).

So the differentiator is four things the shelf tools structurally cannot copy
without the fleet's organs:

1. **Memory & continuity.** "What did we decide three sessions ago" answered from
   a tamper-evident book, not a context window. (Nestor ledger.)
2. **Sealed-canon authority.** The world's truth is a state machine where only a
   **named human** flips the last switch. (terpsi sealing.)
3. **Co-GM, not referee.** The engine proposes a mechanic and the human waves it
   off for the cool thing — mechanics are a **default the DM overrides at will**,
   never a straitjacket.
4. **Auditable joy.** A player's guest character (Bill Cipher) becomes canon by a
   human seal and is then un-retconnable and attributable forever. Non-standard,
   human-authored canon is a *first-class* path, not an exception.

## 3. The CC-BY licence wall

- **SRD 5.1 / 5.2 is CC-BY 4.0.** It may be reused and shipped, but attribution
  is a **hard requirement of the licence**, not a courtesy. Every corpus row
  sourced from the SRD MUST carry its attribution string; `05_corpus.reference.sql`
  enforces this with a CHECK (a `licence='CC-BY-4.0'` row with no attribution is
  refused at write). A row that cannot cite its source is `unknown`, never
  silently included.
- **The reuse/inject split IS a licence and data wall.** Reuse-tier rows (SRD,
  open tables) may live in a shared corpus. Inject-tier rows (a campaign's canon,
  a table's house rules, a family's guests) are **DATA** — they live in the box
  and are never shared, the same blueprint/box wall this whole repo is built on.
- **No fleet nouns leak downward.** Willow, Grove, Nestor, Jeles, SOIL, SAFE —
  none appear in anything a player sees. The engine takes plain domain nouns
  (Ledger, Canon, Roster, Rulings). (Same rule terpsi-music enforces for
  student-facing strings.)

## 4. Reuse specifics (the open shelf)

- **Rules content:** SRD 5.1 (OGL-era, CC-BY 4.0 as re-released) and/or SRD 5.2
  (CC-BY 4.0). Attribution carried per row (§3).
- **Dice:** an MIT-licensed dice roller (e.g. `rpg-dice-roller`) — or the ~30
  lines of stdlib `random` the Vander sims already used. Dice are plumbing; they
  are never stored as knowledge.
- **What we do NOT reuse:** any tool's *DM brain* or *canon store*. That is the
  moat, and it is the fleet's, not the shelf's.

## 5. Inject specifics (the moat — already built)

Each of these exists, is tested, and is currently pointed *outward* — the tax the
fleet pays is rediscovery, and the cure is pointing them here:

- **Nestor `ledger.py` (v0.2.0)** — the hash-chained book of record. The Vander
  dogfood already ran on it (`vander_tracker.py` wrote `ledger.head()/verify()`).
- **terpsi-music `records/sealing.py`** — the PENDING/DRAFT/SEALED/REJECTED
  lifecycle and the `_NOT_A_PERSON` guard. The engine's canon table is this.
- **Nestor `entity.py`** — one referent per name; "the Prince" = "Villippe" =
  "the father" is one entity. Guests ride the same rail.
- **Nestor `decision.py` + `signing.py`** — signed rulings that supersede rather
  than overwrite. House rules and rule-of-cool live here.
- **Jeles corpus + `conflict_scan`** — a verified corpus in front of live search
  that looks for what *refutes*, not what resembles. The corpus reader's shape.

## 6. Closed doors (do not re-propose without addressing the reason)

- **No machine-sealed canon.** Ever. A machine may propose and draft; a named
  human seals. Reopen only with a signed human in the loop, never by relaxing the
  guard. *(Reason: the thesis. A GM that can rewrite the table's truth is not a
  co-GM.)*
- **No campaign data in this repo.** The blueprint refuses data. Reopen never;
  campaigns live in a box. *(Reason: the willow-data-vault pattern, and the
  minors at the table — a family's game is sovereign data.)*
- **No rules-rigor pivot.** The product is not a referee. Reopen only with
  evidence that rigor, not memory+seal+yes-and, is the moat. *(Reason: rigor is
  the shelf's commodity and the model's weakness; §2.)*
- **No SRD row without attribution.** CC-BY is a legal wall, not a style choice.

## 7. What "build" actually is (the seam, scoped)

The only new code is the GM loop and the schemas it runs on (this repo):

1. propose a beat / roll dice / draft a fact → write `PENDING`/`DRAFT` (never
   sealed);
2. surface it to the human DM; on their word, write the `SEALED`/`REJECTED` row
   **with their name**;
3. snapshot the turn into the hash-chained ledger;
4. answer "what's true / what did we decide" from canon + rulings, not from
   memory.

Everything else is reused or injected. That is the whole point of the decision.

---

*Next: a proof-of-concept exhibit — replay the Vander boss room through this
schema (propose the button-is-bait ruling, draft the guest Bill Cipher, seal both
under a named DM, snapshot to the ledger, verify the chain). The dogfood already
did this over a JSONL file; the PoC is the same run over `campaign.db`.*
