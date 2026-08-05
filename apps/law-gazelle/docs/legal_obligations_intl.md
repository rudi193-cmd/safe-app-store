# Law Gazelle — International (Non-US) Legal & Regulatory Obligations Reference

**Prepared:** 2026-08-04 · **Scope:** Non-US jurisdictions only · **Companion document:** a separate agent is covering US federal/state law — not duplicated here.

---

## ⚠️ DISCLAIMER — READ FIRST

**This document is informational research for engineering and product planning. It is not legal advice, was not prepared by a lawyer admitted in any jurisdiction discussed, and must not be relied on as a substitute for jurisdiction-specific legal counsel before any deployment described in this document (especially Deployment Model D2 or D4/E4 "advocate-assisted").** Confidence tags on each claim (SETTLED / CONTESTED / UNCERTAIN) reflect the state of publicly available legal authority as researched via web search on 2026-08-04, not a formal legal opinion. Several fast-moving areas (EU AI Act, India's DPDP Rules, Australia's Privacy Act reform) changed materially in 2025–2026 and may change again before this document is acted on — re-verify dates before relying on any deadline stated here. Do not deploy Law Gazelle to real clients in any jurisdiction below without actual counsel.

---

## Provenance — what was checked, and what was not

Produced by a dedicated research pass on 2026-08-04 and reviewed before
landing. Companion: [`legal_obligations_us.md`](legal_obligations_us.md).

**Independently verified on review** — the Digital Omnibus deferral in §3, because
it is load-bearing and post-dates the reviewer's own knowledge. Confirmed: the
Council gave final approval **29 June 2026** (Parliament endorsed 16 June 2026,
423–57 with 174 abstentions); **Annex III standalone high-risk obligations move
to 2 December 2027** (a 16-month deferral) and Annex I embedded-product systems
to 2 August 2028. Confirmed too, and the more important half: **Art. 50
transparency duties are unchanged and live now**, as is the **Art. 4 AI-literacy
duty** — the deferral buys nothing on either. The package also adds SME and
small-mid-cap definitions with simplified technical documentation and priority
sandbox access, which is likely relevant to a nonprofit deployer.

**Not verified:** the exact regulation number cited for the Omnibus. The
substance above is confirmed; treat the citation number as needing a look before
it goes in front of counsel. No other citation in this document was
independently re-verified.

**The Annex III conclusion is a reasoned engineering position, not a legal
classification.** The document says so itself and gives two independent lines of
reasoning; both are argued from commentary and recital rationale, not from any
decided case. Note especially its own flip condition: **MISSION.md names court
self-help centers as a distribution channel, and some are staffed by court
employees** — which is exactly the fact pattern that makes "on behalf of a
judicial authority" genuinely hard. That is a live collision between the stated
channel and the favorable classification, not a hypothetical.

**Shallow by the author's own admission:** France, the Netherlands, South Korea,
Japan, PIPL's application to passive open-source distribution, and whether the
EAA / EN 301 549 reach this service category at all.

---

## 0. What the app actually is (grounding facts used throughout)

Read from `apps/law-gazelle/MISSION.md`, `README.md`, `safe-app-manifest.json`, `docs/law_gazelle_spec.md`, and `docs/law-gazelle-expansion.md`:

- **Local-first, offline, no server, no account, no network egress by default.** `privacy_tier: client_only`, `local_processing: 1.0` in the manifest. Data lives in SQLite on the user's own machine.
- **Two-store model**: canonical case data ("Nest") is operator-provided and **read-only** to the app; all app writes go to a separate sidecar DB (`gazelle_state.db`), except explicit drafts and session commit manifests written back to Nest.
- **Three matter types compiled in**: family law/custody-co-parenting (necessarily contains **minors' data**), consumer bankruptcy/insolvency (**financial data**), workers' compensation (**health data** — GDPR Art. 9 special category).
- **Functionally**: computes/surfaces deadlines, browses documents/evidence, builds chronologies, assembles drafting context. Per MISSION.md Principle 2 and the spec's `_fact_blocked` gate in `workflow.py`: **it never authors case facts, never applies law to facts, never recommends strategy or predicts outcomes**, and unverified facts are gated out of drafting.
- **Optional AI**: local Ollama model only (default `llama3.2:3b`). No cloud model call, no data leaves the device for AI processing either.
- **MCP surface**, with an **optional, off-by-default** WillowGate authorization layer (trust-tiered, PGP-ledgered, denies-by-default when enabled).
- **MIT licensed**, published as public source on GitHub (`rudi193-cmd/safe-app-store`), synthetic examples only in the public repo.

### Deployment models (obligations differ enormously — used as a tag throughout: **D1 / D2 / D3**)

| Model | Description | Who is the GDPR "controller"? |
|---|---|---|
| **D1** | Individual self-represented litigant runs it on their own machine over their own case | The individual — but see Art. 2(2)(c) household exemption analysis §1.5 |
| **D2** | A legal aid clinic, law firm, or advice organization runs it on behalf of clients | The organization (controller); possibly joint with any advocate individually |
| **D3** | The software is published (MIT, on GitHub) and downloaded/run by unknown third parties | The publisher is normally **not** a controller/processor at all (see §8) — the deploying user or org is |

---

## Executive Summary — Top 5 Exposures, Ranked

1. **EU AI Act — Annex III "administration of justice" high-risk classification is a live, non-trivial question, but the better-reasoned answer is NOT high-risk for D1/D2 today** — because Annex III §8(a) is scoped to systems used *by a judicial authority or on its behalf* (or in ADR), not systems used by a litigant or their adviser preparing their own case, and because Law Gazelle's own design principle (never applies law to facts) keeps it out of the "researching/interpreting facts and law and applying law to facts" function even if that line moved. **Confidence: CONTESTED** — this is the single largest classification judgment call in the document, turns on a phrase ("or on their behalf") that has not been tested in court, and a future E3/E4 "advocate-assisted" or intake-automation direction could change the analysis materially. See §3.

2. **Germany — unauthorized legal services (RDG) risk is real and specifically shaped by German case law (wenigermiete.de / Conny), and it bites hardest at D2/E4 (advocate/clinic-run) scale, not D1.** A tool that only organizes a person's *own* matter is not "legal services" under RDG's own-affairs carve-out; a tool operated *by* an organization *for* clients starts to look like the regulated activity the RDG line of cases scrutinizes, especially if any output edges toward assessment rather than organization. **Confidence: SETTLED** on the general RDG "own affairs" exemption; **CONTESTED** on exactly where Law Gazelle's drafting-context assembly sits relative to it at scale. See §4.

3. **GDPR Art. 9 special-category data (custody = minors + possible Art. 10 criminal-conviction-adjacent data in family violence contexts; workers' comp = health data) makes this a "special category, D2 = large-scale processing likely" situation the moment it's operated by a clinic — triggering mandatory DPIA (Art. 35), Art. 30 records, and a live question about which Art. 9(2) ground actually clears the bar.** Art. 9(2)(f) (legal claims) is the best-fit ground but is not unlimited, and D1's household exemption (Art. 2(2)(c)) almost certainly does **not** extend to D2. **Confidence: SETTLED** on the DPIA trigger at D2 scale; **CONTESTED** on whether Art. 9(2)(f) alone covers all processing purposes (e.g., organizing evidence not yet tied to an actual claim). See §1.

4. **England & Wales / Legal Services Act 2007 reserved-activities scheme is narrow and mostly does NOT catch Law Gazelle even at D2/E4 scale** — "conduct of litigation" and "rights of audience" are the two reserved activities in play, and case organization/drafting-context tools performed by non-solicitors for self-represented litigants sit in the large unregulated space the SRA itself has flagged as under-supervised. This is a **lower** exposure than Germany, but the SRA's public warnings about unregulated AI-adjacent legal tech make it worth naming precisely because regulators are actively watching this exact category. **Confidence: SETTLED** on the narrow scope of reserved activities; **UNCERTAIN** on SRA's future direction, which is stated as a live policy concern rather than settled law.

5. **Cross-border/extraterritorial GDPR exposure for the D3 publisher is very likely nil, but D2 deployers anywhere the app reaches EU/UK/EEA data subjects inherit full GDPR/UK GDPR controller obligations regardless of where the deploying organization is physically located (Art. 3(2) targeting test).** The local-first architecture is a genuine mitigant for transfer risk (Chapter V) but does **not** exempt a D2 controller from Art. 30 records, Art. 35 DPIA, Art. 33/34 breach notice, or DSAR fulfillment obligations — those attach to *any* controller processing EU/UK residents' data, wherever the controller sits. **Confidence: SETTLED** on the targeting test itself; **UNCERTAIN** on enforcement likelihood against small/nonprofit clinics in practice (a practical, not legal, uncertainty).

---

## 1. EU/EEA — GDPR (Regulation (EU) 2016/679)

### 1.1 Lawful basis architecture (Art. 6 + Art. 9)

GDPR requires **two** legal bases for special-category data: a general Art. 6(1) basis *and* a separate Art. 9(2) condition lifting the Art. 9(1) prohibition. **Confidence: SETTLED.**

- **Art. 6(1) basis, D1**: most plausibly (b) performance of a contract to which the data subject is party (weak fit — no contract with a piece of local software) or, more defensibly, the household exemption removes GDPR from the picture entirely (§1.5) — meaning Art. 6 analysis may not even be reached at D1.
- **Art. 6(1) basis, D2**: (f) legitimate interests (the clinic's interest in delivering its service) is the standard fit for advice organizations, sometimes (c) legal obligation where a bar/legal-aid regulatory scheme requires case record-keeping. Consent (a) is disfavored here — the power imbalance between a legal-aid client and the organization makes GDPR consent hard to establish as "freely given" per Art. 4(11)/Recital 43 and EDPB guidance on consent in unequal relationships.
- **Art. 9(2) condition — the harder question**:
  - **Art. 9(2)(f) — "necessary for the establishment, exercise or defence of legal claims"** is the best-fit condition for the custody and workers'-comp data specifically because those matters *are* legal claims or proceedings. **Confidence: SETTLED that (f) exists and fits the core use case; CONTESTED on scope** — (f) covers data necessary for the claim, but a case-command-center that ingests *all* evidence, correspondence, and context (not only what is strictly "necessary" for the specific claim) risks processing that outruns (f)'s necessity boundary. Some material (general chronology-building, non-claim-related family context) may need a second condition or minimization discipline to stay inside (f).
  - **Art. 9(2)(a) explicit consent** could cover the gap, but explicit consent standards are demanding (freely given, specific, informed, unambiguous, revocable) and awkward for the clinic-client relationship noted above.
  - **Art. 9(2)(g)** (substantial public interest, Member State law) could apply to legal-aid-adjacent processing in some Member States that have specific legal-aid data-protection legislation, but this is Member-State-specific and not researched jurisdiction-by-jurisdiction here — **flagged as an open question requiring local counsel** in each Member State of deployment.
  - **Engineering implication**: the app's existing minimization posture (organize, don't infer; verify before draft) is a genuine Art. 9(2)(f) *necessity* ally — the tighter the tool keeps itself to claim-relevant material, the stronger the (f) argument.

### 1.2 Controller / processor / joint controller across D1/D2/D3

**Confidence: SETTLED framework, CONTESTED application to this specific architecture.**

- **D1**: the individual is both data subject and (if GDPR applies at all — see §1.5) controller of their own data; there is no separate processor because the software does not transmit data to anyone, including the publisher.
- **D2**: the organization is the controller. The **individual advocate** operating the tool inside the organization is not typically a separate controller (acting within employment/engagement scope), though bar rules in some Member States create individual professional-responsibility duties layered on top of the organizational GDPR duties (these are separate legal regimes — see §5).
- **D3 (publisher)**: normally **not** a controller or processor at all, because the publisher never receives, stores, or has access to any deployer's data — there is no "processing" by the publisher within Art. 4(2) to found either role. This is the single most protective fact in the app's architecture from a GDPR-exposure-to-the-publisher standpoint. **Confidence: SETTLED as a matter of GDPR's processing definition; UNCERTAIN whether a regulator would ever test this** because it has not been the subject of a reported enforcement action against a pure local-software publisher of this shape.
- **No joint-controller relationship exists between D3 publisher and any D1/D2 deployer** under the *Wirtschaftsakademie*/*Fashion ID* joint-controllership tests (which require some *jointly determined* means/purposes) — the publisher does not determine the purposes or means of any specific deployer's processing; it only writes code the deployer chooses whether and how to run.

### 1.3 Art. 30 records of processing

**Confidence: SETTLED.** Required of any controller/processor with >250 employees, **or** (the exception that actually matters here) whose processing is not occasional, includes special-category data, or is likely to result in a risk to data subjects' rights (Art. 30(5)). D2 clinics processing custody/health/financial special-category data as their core activity **must** keep Art. 30 records regardless of size — the small-organization exemption does not apply once special-category data is processed non-occasionally. D1 is out of scope if the household exemption holds (§1.5); if it doesn't, an individual isn't a GDPR "controller" required to maintain Art. 30 records in the way an organization is, though the substantive Art. 5/6/9 obligations would still attach.

**Engineering/product implication**: for any D2 build, the app or its deployment guide should be able to **produce a machine-readable inventory** of: categories of data subjects (clients, minors, opposing parties named in evidence), categories of data (special-category flags per matter type), purposes, retention, and recipients (none, if egress stays off) — largely derivable automatically from the existing `data_streams` block in `safe-app-manifest.json`, which is a good start but is written for the *software's* own operational state, not yet shaped as an Art. 30 controller record for a *deploying organization's* processing of *client* data.

### 1.4 DPIA (Art. 35)

**Confidence: SETTLED that DPIA is triggered at D2 scale.** Mandatory where processing is "likely to result in a high risk," with three enumerated triggers directly relevant here: (i) large-scale processing of special-category data (custody/health data, at clinic scale, easily reaches "large scale" under WP29's factors — number of data subjects, volume, duration, geographic extent); (ii) systematic and extensive evaluation producing legal/similarly-significant effects (the deadline-ranking/urgent-queue AI feature is evaluative — see Art. 22 analysis §1.7, which feeds directly into whether this trigger is met); (iii) not directly about public monitoring, so less relevant here.

A **DPIA is very likely legally required before any D2 deployment**, and should assess: the necessity/proportionality of Art. 9(2)(f) reliance, risks from the minors'-data and health-data processing, the mitigations the local-first architecture already provides (no egress = no transfer risk, no cloud AI = no third-party processor risk), and residual risk from the **sidecar being the one place the app writes durable state about a human's judgment** (notes, resolutions, AI cache).

D1 likely does not require a DPIA (no "controller" in the Art. 35 organizational sense if Art. 2(2)(c) applies; and even if it did, DPIA is a controller obligation triggered by risk to *others'* rights primarily, and a self-represented litigant organizing their own matter is a much lower-risk fact pattern).

### 1.5 The household exemption at D1 (Art. 2(2)(c))

**Confidence: CONTESTED — this is a load-bearing, unresolved question for D1.**

Art. 2(2)(c) excludes "processing by a natural person in the course of a purely personal or household activity." CJEU authority (*Rynes* C-212/13, *Buivids* C-345/17) reads this exemption **narrowly** and cuts it off the moment the activity has any effect reaching outside the person's private sphere. Two features of Law Gazelle's own fact pattern cut against a clean household exemption at D1:

- The data necessarily includes **third parties who are not the user**: a co-parent, children, employers, insurers, opposing counsel — people whose data the litigant is processing but who are not part of the litigant's "household."
- The purpose is not purely domestic — it is preparation for formal legal proceedings, an activity with an inherent outward-facing legal effect (filings, court submissions, service on the other party).

Countervailing: *Rynes* and *Buivids* were about surveillance/publication cases where data plainly left the personal sphere (a camera facing the street; a public video). A self-represented litigant organizing *their own case file* on their own machine, disclosing nothing to anyone until they choose to file it, is a materially different fact pattern the CJEU has not directly addressed. **No case squarely on point was found.** **What would resolve this**: a national DPA guidance note or CJEU reference addressing personal case-management software for self-represented litigants specifically — none identified in this research.

**Practical takeaway**: do not build D1 messaging or a compliance posture that *assumes* the household exemption clearly applies. Treat D1 as "probably out of full GDPR scope, but not certainly" and keep the local-first architecture strong regardless — it is what would make GDPR-in-scope-at-D1 low-consequence even if the exemption fails, since there is no third-party processor, no transfer, and minimal Art. 30/35 burden for a single individual's own matter in practice (enforcement realism, not legal certainty).

### 1.6 Art. 25 — data protection by design and by default

**Confidence: SETTLED as a framework; this is the section where the app's architecture does real, demonstrable work.**

Art. 25 requires technical/organizational measures implementing data-protection principles (minimization, purpose limitation, storage limitation) **at the time of determining the means of processing and at the time of processing itself**, and Art. 25(2) specifically requires that, by default, only data necessary for each specific purpose is processed, and that personal data is not made accessible without the individual's intervention to an indefinite number of people.

**The architecture already substantially satisfies Art. 25**, and this should be documented affirmatively rather than only defended reactively:
- **No network egress by default** → data is never made accessible to an indefinite number of people; satisfies Art. 25(2)'s accessibility limb almost by construction.
- **Read-only canonical store, sidecar-only writes** → purpose limitation and integrity are structurally enforced, not policy-enforced; an app bug cannot silently corrupt the canonical case record.
- **No account, no cloud AI by default** → no third-party processor relationship to manage, audit, or contract (no Art. 28 DPA needed unless/until a deployer chooses cloud AI, which is explicitly not the default).
- **Mandatory human fact-verification gate (`[VERIFY]`/`[FACT NEEDED]`, `_fact_blocked`)** → this is a genuine Art. 25 "by design" accuracy control (Art. 5(1)(d) accuracy principle) baked into the data model, not a UI suggestion.
- **Dormant WillowGate authorization ledger** → when turned on, provides exactly the kind of access-logging and least-privilege control Art. 25/32 point toward; being *off by default* at D1 is defensible (single user, own data), but **should not stay off by default at D2/E4** (see §1.9 and the Art. 32 security note below) — this is a genuine gap once the deployment model changes, not a permanent design virtue.

**Gap to flag**: Art. 25 by-design analysis has not yet been done *on paper* as a documented DPIA-style artifact — the architecture does the right things, but there is currently no artifact a regulator or partner org could review to confirm that. That artifact is cheap to produce given how much of the answer already exists in the codebase's own design principles.

### 1.7 Data subject rights vs. an append-only/read-only canonical store

**Confidence: SETTLED on the rights; CONTESTED/UNCERTAIN on how cleanly this architecture satisfies them at D2 scale.**

- **Right of access (Art. 15)**: straightforward for a D2 controller — the canonical Nest DB, sidecar DB, and AI cache together constitute the full record; producing a subject access response is a data-export problem, not a legal-basis problem. The app currently has no built-in DSAR-export tool; this is a **product gap**, not a legal gap — the data is locally queryable so building the export is low-effort relative to most SaaS DSAR problems.
- **Right to erasure (Art. 17)**: this is where the read-only-canonical-store design creates real tension. If a data subject (e.g., a named opposing party, or a minor represented by someone other than the litigant) exercises Art. 17, the canonical Nest store is explicitly **not writable by the app** — by design, only the operator/legal-work-session process writes there. That means erasure, if it must happen, happens **upstream of Law Gazelle**, in Nest itself, not inside the app. The **sidecar** (notes, AI cache, resolved/snoozed state) *is* writable and erasure-capable. **Practical implication**: a D2 deployer's erasure-request procedure cannot terminate inside Law Gazelle; it must reach into Nest. This should be documented explicitly in any D2 deployment guide — "erasure requests are fulfilled at the Nest layer, not the app layer" — so a clinic doesn't discover this gap during an actual complaint.
  - Countervailing consideration: Art. 17(3)(e) exempts erasure where necessary for the establishment, exercise, or defence of legal claims — the same ground as Art. 9(2)(f) — so a case still open or on appeal has a real argument against erasure of case-relevant material regardless of store architecture. This mitigates but does not eliminate the architectural gap (closed/abandoned matters, or third parties' data not needed for the claim, remain squarely erasable).
- **Right to data portability (Art. 20)**: strong fit — SQLite + JSON export is already a structured, machine-readable, commonly-used format, which is Art. 20's own test. This is a case where the architecture is *already* portability-compliant essentially by construction.
- **Right to rectification (Art. 16)**: same tension as erasure — rectifying the canonical store is upstream of the app; the sidecar's `[VERIFY]`/note layer is actually a reasonable rectification-adjacent mechanism (flagging disputed facts without silently rewriting the canonical record), which is defensible as a design choice but should be described to a regulator as "how rectification requests are handled," not left implicit.

### 1.8 Art. 33/34 — breach notification and the 72-hour clock

**Confidence: SETTLED on the rule; the architecture materially reduces (does not eliminate) the practical breach surface.**

Art. 33 requires notifying the supervisory authority within 72 hours of becoming aware of a breach likely to risk data subjects' rights (D2 controller obligation); Art. 34 requires notifying affected individuals directly where the risk is *high*. Given the special-category data involved (health, and de facto sensitive family-law/minors data), a breach at D2 scale would likely cross the Art. 34 "high risk" threshold, not just the Art. 33 threshold — meaning individual notification, not just regulator notification, is the realistic bar.

- **Where the local-first design helps**: no server means no server-side breach vector (no SQL injection against a hosted DB, no cloud misconfiguration, no third-party processor breach to chain from). The attack surface for a D2 deployment is the **advocate's own machine(s)** — device theft, malware, misconfigured backup, or a WillowGate misconfiguration if the gate is enabled but weakly secured.
- **Where it does not help**: **72-hour awareness detection is materially harder without central logging or telemetry.** A D2 clinic running this on staff laptops with no phone-home telemetry has no automated way to detect a breach (e.g., a stolen laptop, a misdirected export) except human report. This is a real product/ops gap for D2/E4: **the app currently has no local breach-relevant audit trail beyond the dormant WillowGate ledger**, which is off by default. **Engineering implication**: a D2-oriented build should treat WillowGate (or an equivalent local audit log) as load-bearing for breach-detection capability, not merely for authorization — an organization cannot certify a 72-hour clock they have no way of starting.

### 1.9 Art. 22 — automated decision-making

**Confidence: CONTESTED — reasoned conclusion below, but this is a genuine judgment call.**

Art. 22(1) prohibits decisions **based solely on automated processing, including profiling,** that produce **legal effects** or **similarly significant effects**, absent an Art. 22(2) exception.

Applying this to Law Gazelle's two candidate features:

- **Deadline computation/ranking (urgent queue)**: this is **not** a decision "concerning" the data subject in the Art. 22 sense at all in the D1 case — it is the user's own tool computing dates from their own case data for their own use, with the user free to act or not act on the output; there is no decision being *made about* a person by an external party. In the D2 case, the same logic mostly holds — the deadline ranking assists the advocate's own workflow prioritization; it does not, by itself, produce or communicate a legal/significant effect to the client absent further human action (the advocate deciding what to file, when). **This is deterministic date computation, not profiling** in the sense the article targets — Art. 22 is aimed at automated *judgment calls about a person*, and a deadline is a computed fact, not an evaluative judgment. Low risk.
- **AI ranking/briefing/fact-inspection (the local-LLM features)**: this is closer to the line, because it involves an LLM producing an evaluative output (a priority ranking, a briefing synthesis, a fact-plausibility inspection) that a human could, in principle, act on without further scrutiny. **Two facts pull this back from Art. 22 exposure**: (1) the app's explicit human-verification gate means AI output is never the final word — a human confirms facts before they reach a draft, and no automated output "decides" anything with legal effect on its own; (2) even in the D2/advocate case, the advocate — not the AI — remains the one who files, argues, or advises, meaning there is always **meaningful human involvement** between AI output and any legally effective decision, which is exactly what takes processing outside Art. 22(1) per the accepted EDPB/ICO reading (human involvement must be a genuine, qualified, empowered review, not rubber-stamping — and here it's *structural*, not just procedural, because drafting is *gated* on verification).
- **Where this could flip**: if a future direction lets AI output flow into a filing, decision, or client-facing recommendation *without* the human-verification gate in the loop (e.g., an automated triage that silently deprioritizes a matter, or a scoring feature a clinic uses to allocate advocate time among clients without human review), that specific feature would need fresh Art. 22 analysis — the gate is what currently keeps the app on the safe side, and it is a **product decision**, not an inherent architectural guarantee, so it must remain load-bearing as new AI features are added (E2 matter-type generalization, E3 guided intake).

### 1.10 Chapter V — international transfers

**Confidence: SETTLED, and this is a clean win for the architecture.** Chapter V governs transfers of personal data to third countries. With no network egress by default and no cloud AI by default, **there is no transfer to analyze in the default configuration** — Chapter V simply does not engage. This is worth stating as an affirmative compliance property, not just an absence of a problem: most GDPR programs spend significant effort on SCCs, transfer impact assessments, and adequacy analysis, and the default architecture here needs none of that. **The only way Chapter V re-enters the picture** is if a deployer (a) switches on a cloud AI model instead of local Ollama, (b) syncs Nest to a cloud backup located outside the EEA/UK/adequate countries, or (c) an MCP client connecting to the server itself runs on infrastructure outside the EEA. All three are deployer choices outside the shipped default and should be flagged in any D2 deployment guide as "the moment you change this, Chapter V applies to you."

### 1.11 Art. 10 — criminal-conviction/offence data

**Confidence: SETTLED on the rule; CONTESTED on whether it is actually engaged here.**

Art. 10 restricts processing of criminal-conviction/offence data to processing "under the control of official authority" or where authorized by Union/Member State law with appropriate safeguards. Custody/co-parenting matters can, in practice, involve **allegations** of domestic violence, child abuse, or criminal conduct by a party — and EDPB guidance reads Art. 10 broadly enough to cover not just formal convictions but allegations and investigation-adjacent information that implies criminal wrongdoing.

If custody-matter data ingested into Law Gazelle includes such allegations (very plausible in real custody litigation), **Art. 10 is likely engaged for that subset of data**, which is a **second, independent** special-category-style constraint layered on top of the Art. 9 analysis (Art. 10 is not technically "special category" under Art. 9, but is subject to comparably strict Art. 10 control). Because a D2 legal-aid clinic or law firm is not "official authority" in the Art. 10 sense, the lawful path is the "authorized by Member State law" limb — meaning **this is genuinely Member-State-specific** and not something this document can resolve generally: several Member States have specific statutory authorizations for lawyers/legal-aid bodies to process criminal-allegation data in the course of representation, but the exact scope varies. **Flagged as an open question requiring per-Member-State counsel** for any D2/E4 deployment touching custody matters with abuse allegations — which, realistically, is a meaningful share of real custody litigation.

---

## 2. United Kingdom — UK GDPR and Data Protection Act 2018

**Confidence: SETTLED on the general parallel-regime structure; SETTLED on the specific 2025 reform details below (recent primary-source-adjacent reporting).**

Post-Brexit, the UK runs a substantively similar but formally separate regime (UK GDPR + DPA 2018), enforced by the ICO rather than an EU supervisory authority + EDPB. All of §1's analysis (lawful basis, controller/processor, Art. 30, DPIA, Art. 25, DSARs, breach, Art. 22, transfers) applies in near-identical form under the UK GDPR's mirrored article numbering, **with the following material divergences** introduced by the **Data (Use and Access) Act 2025** (royal assent 19 June 2025):

- **Automated decision-making (Art. 22 equivalent) has been narrowed in the UK's favor of controllers**: the Act broadens the circumstances in which ADM is permitted where **no special-category data is involved**, and allows reliance on "legitimate interests" as a lawful basis for such ADM. **This does not help Law Gazelle's AI features directly**, since the matters in question (custody, health) are precisely the special-category cases the reform did *not* loosen — the UK reform's ADM relaxation is narrower than it might first appear for this app's fact pattern.
- **New "recognised legitimate interests" list** (Art. 6 equivalent) — a no-balancing-test lawful basis for specific purposes (public-body requests, safety, crime prevention). Not obviously on point for Law Gazelle's core processing, but worth checking against any future law-enforcement/safeguarding-adjacent feature.
- **DSAR scope narrowed to "reasonable and proportionate" search** — codifies existing case law/ICO guidance; **helps** a D2 deployer, since it caps the search burden a DSAR imposes rather than requiring an exhaustive trawl of every sidecar table and AI cache entry.
- **New direct "right to complain" to the controller** — a D2 clinic needs an internal complaint-handling process distinct from (and prior to) referring a complainant to the ICO. **Product/ops gap**: no such workflow currently exists in the app; this is an organizational, not software, requirement, but worth naming in a D2 deployment checklist.
- **International transfer test loosened**: a new UK "data protection test" replaces the EU's stricter "essentially equivalent" adequacy standard with more flexibility — marginally relevant only if a deployer chooses non-UK cloud AI or backup, consistent with §1.10.
- **PECR penalty alignment** (fines raised to UK GDPR levels) — not directly relevant (PECR concerns electronic marketing/cookies, which this app does not do).

**Net UK conclusion**: the UK regime is not more permissive for Law Gazelle's actual special-category processing; it is more permissive for *non-special-category* ADM and DSAR burden generally, neither of which changes the core analysis in §1.

---

## 3. EU AI Act (Regulation (EU) 2024/1689, as amended by the Digital Omnibus, Regulation (EU) 2026/1744)

**This is the sharpest and most consequential piece of non-US regulatory analysis in this document. Read carefully — the classification conclusion below is a genuine judgment call, not a settled fact.**

### 3.1 Current timeline (as of 2026-08-04) — **Confidence: SETTLED**, verified against 2026 reporting

- **Digital Omnibus on AI** (Regulation (EU) 2026/1744) was published in the Official Journal on 24 July 2026 and entered into force 27 July 2026, following European Parliament endorsement (16 June 2026) and Council final approval (29 June 2026).
- **2 August 2026**: Article 50 transparency obligations (chatbots, synthetic-content labeling, deepfakes) take effect **on schedule — this deadline was not postponed.**
- **High-risk Annex III (stand-alone systems) obligations postponed from 2 August 2026 to 2 December 2027.**
- **High-risk Annex I (AI embedded in already-regulated products) obligations postponed to 2 August 2028.**
- **Prohibited-practices provisions (Art. 5)** and **GPAI provider obligations (Art. 53 et seq.)** were already in force from earlier 2025 milestones and are unaffected by this postponement.

**Practical read for Law Gazelle**: even under the *most* high-risk-favoring interpretation of Annex III §8 below, there is no live high-risk compliance deadline until **December 2027** — this gives real runway to resolve the classification question properly (ideally with counsel) rather than under deadline pressure. The **Art. 50 transparency deadline (already in force as of August 2026) is the one live obligation regardless of the high-risk question** — see §3.4.

### 3.2 Is Law Gazelle "administration of justice" high-risk under Annex III §8? — **Confidence: CONTESTED, reasoned conclusion: likely NOT high-risk for D1/D2 as currently built**

Annex III point 8(a) (as commonly rendered from the regulation, cross-checked against Recital 61's framing): AI systems intended to be used **"by a judicial authority or on their behalf"** to research and interpret facts and law and apply law to facts, or used similarly in alternative dispute resolution. Recital 61 grounds this in protecting judicial independence, the rule of law, and the right to a fair trial — concerns specific to the *court's own* decision-making process — and separately carves out purely ancillary administrative activities (e.g., anonymization, internal communications) that don't affect the actual administration of justice in individual cases.

**Two independent lines of reasoning point away from high-risk classification**, and it is worth having both because they don't depend on each other:

1. **The "used by/on behalf of a judicial authority" limb.** Law Gazelle is used by a **litigant (D1)** or their **advocate/clinic (D2)** — never by a court, tribunal, or ADR body, and never *on behalf of* one. Multiple independent commentary sources converge on reading "on their behalf" as meaning an entity performing the judicial authority's *own* function (e.g., an outsourced court analytics unit), not a party's private preparation tool — "the critical distinction is whether the system is being used by a judicial authority versus used by lawyers for their own purposes," and the latter is described as falling *outside* Annex III §8 by commentators surveyed. **No EU court or Commission guidance has yet tested this boundary directly against a self-represented-litigant tool**, which is why this remains CONTESTED rather than SETTLED — but the direction of the available commentary and the recital's stated rationale (protecting the judicial *decision-making process itself*) both point the same way.
2. **The functional-scope limb, independent of who uses it.** Even setting aside *who* runs it, Annex III §8(a)'s trigger is a system that **researches/interprets facts and law and applies law to a concrete set of facts.** Law Gazelle's own design principle — stated in MISSION.md ("does not apply law to facts, recommend strategy, or predict outcomes") and enforced in code (`_fact_blocked` gate) — means the *shipped* product does not perform the function the article describes, **by the same logic Article 6(3)'s narrow-procedural-task carve-out uses** for systems that don't themselves perform the qualifying Annex III function (e.g., a "generative writing assistant performs none of the Annex III functions ... and is not high-risk under Annex III on that basis," per commentary on analogous tools).

**Where this conclusion could flip, and should be re-checked before shipping**:
- **E3 (guided intake with structured fact extraction) or E4 (advocate-assisted at clinic scale)** could push the tool closer to "interpreting facts and law" if a future feature moves from *organizing* facts to *characterizing* them (e.g., an AI feature that scores case strength, predicts a custody outcome, or auto-classifies a fact pattern against legal standards) — that would revisit both limbs of the analysis above.
- **If Law Gazelle is ever adopted by a court's self-help center in a capacity where the center is acting in a quasi-official capacity** (some court self-help centers are staffed by court employees), the "on behalf of a judicial authority" question gets genuinely harder and should be re-evaluated specifically for that deployment, not assumed to inherit the D1/D2 analysis above.
- This conclusion is a **reasoned position for engineering/product planning purposes, not a certified legal classification** — given the stakes (high-risk status triggers conformity assessment, technical documentation, a registered EU database entry, and Art. 26 deployer obligations), **actual counsel should confirm this before any D2/E4 deployment**, especially once a named pilot partner is in the picture (per `law-gazelle-expansion.md` E4/finish-list C-5).

### 3.3 If it WERE high-risk — what that would concretely require (for planning purposes, not asserted as applicable today)

Documented here so the gap between "not high-risk today" and "what high-risk would cost" is visible for future roadmap decisions:

- **Risk management system** (Art. 9) — a formal, documented, continuously updated risk process across the AI system's lifecycle.
- **Data governance** (Art. 10) — training/validation/testing data quality, bias examination, representativeness — largely N/A for a locally-run third-party model (Ollama/llama3.2) the app doesn't train, but relevant to any fine-tuning or prompt-engineering the app layer does.
- **Technical documentation** (Art. 11) and **record-keeping/logging** (Art. 12) — the dormant WillowGate ledger is a genuine head start here if turned on; it would need to become mandatory, not optional, under a high-risk posture.
- **Transparency to deployers** (Art. 13) — already well-served by the app's local, inspectable, open-source nature.
- **Human oversight** (Art. 14) — **already substantially satisfied**: the `[VERIFY]`/`_fact_blocked` gate and the requirement that a human confirm facts before drafting is a textbook Art. 14 human-oversight control (able to understand capabilities/limitations, remain aware of automation bias, able to decide not to use output, able to intervene/stop). This is the clearest example in the whole document of the architecture pre-satisfying a real obligation.
- **Accuracy, robustness, cybersecurity** (Art. 15).
- **Conformity assessment + EU database registration** (Arts. 43, 49) — the heaviest lift; would likely require a self-assessment (internal control) route for most Annex III §8-type systems rather than third-party assessment, but still a substantial new compliance program.
- **Deployer obligations (Art. 26)** would fall on the D2 clinic/firm, not the D3 publisher — another point where the publisher/deployer split (§below, and see the running distinction throughout this document) matters.

### 3.4 Art. 50 transparency obligations — **Confidence: SETTLED, and this IS a live, in-force obligation as of 2 August 2026**

Independent of the high-risk question, **Article 50 is already in force and is the concrete near-term action item.** Art. 50(1) requires providers of AI systems intended to interact directly with natural persons to ensure people are informed they're interacting with an AI system (unless obvious from context) — persistent, clear disclosure (not buried in a ToS, not just a technical marker). Art. 50(2) governs AI-generated/synthetic content labeling.

**Applied to Law Gazelle**: the AI briefing/ranking/drafting-context/fact-inspection features are exactly the kind of AI-generated output Art. 50 contemplates. **Mitigating facts**: it's a TUI the user deliberately invokes (arguably "obvious from context" that AI-inspect/AI-brief is AI, given the explicit key command and cache-preflight UI), and the mandatory human-verification gate before anything reaches a draft is close to the kind of "editorial control" exemption contemplated for Art. 50(2)-adjacent content-labeling relief. **Engineering implication — low-cost, do this regardless of the high-risk question**: add a persistent, visible label (not just a UI convention) on every AI-generated briefing/ranking/draft-context surface stating it is AI-generated and requires verification — this is cheap, already aligned with the product's own "verify everything" principle (MISSION.md Principle 3), and closes the one AI Act obligation that is unambiguously in force today regardless of how §3.2's classification question resolves.

### 3.5 GPAI obligations — **Confidence: SETTLED, and this does not attach to Law Gazelle**

Law Gazelle is a **downstream deployer of a third-party open-source model (Ollama/llama3.2)**, not a GPAI **provider** — it doesn't train, fine-tune, or redistribute the model under its own name. GPAI provider obligations (Art. 53: technical documentation, training-content summary, copyright policy) attach to whoever provides the *model* (Meta, for Llama; Ollama as a runtime is not itself "providing" a GPAI model in the Art. 53 sense either). **No GPAI obligation attaches to the Law Gazelle publisher or any deployer** under the current architecture. This would change only if Law Gazelle started shipping or fine-tuning its own model — not the current design.

---

## 4. Unauthorized / Reserved Legal Practice Outside the US

### 4.1 England & Wales — **Confidence: SETTLED on statutory scope; UNCERTAIN on regulatory direction**

The Legal Services Act 2007, s.12, defines exactly **six reserved legal activities**: rights of audience, conduct of litigation, reserved instrument activities (real property), probate activities, notarial activities, administration of oaths. **Everything else is, by construction, unregulated** and open to any person or entity — this is a much narrower reserved zone than US unauthorized-practice-of-law doctrine, which tends to sweep in "giving legal advice" generally.

- Law Gazelle's functions (organizing evidence, computing deadlines, assembling drafting context, browsing documents) **do not fall within any of the six reserved activities** at either D1 or D2 — it neither exercises rights of audience nor "conducts litigation" (a term of art meaning formally issuing/prosecuting proceedings, not preparing for them).
- **The live regulatory concern is not statutory scope but SRA policy attention.** The Solicitors Regulation Authority has publicly flagged unregulated legal-tech/AI providers as an access-to-justice and consumer-protection gap precisely *because* the reserved-activities net is narrow — consumers of unregulated tools have none of the protections (insurance, complaints scheme, compensation fund) that come with regulated legal services. This is a **policy/reputational** exposure more than a **legal** one today: Law Gazelle is lawful to operate unregulated, but an advice organization (D2) presenting it to clients should be transparent that it is *not* a source of regulated legal advice, consistent with MISSING.md's own "information, not advice" framing — which is already the right posture, and should be stated explicitly in any client-facing D2 deployment, not just implied by the tool's internal design.
- **What would change this**: if a future feature crossed into "conduct of litigation" (e.g., an automated e-filing feature that itself issues or manages proceedings on the litigant's behalf without the litigant's own action) — not present in the current design, but worth flagging as an E3/E4 boundary to watch.

### 4.2 Germany — Rechtsdienstleistungsgesetz (RDG) — **Confidence: SETTLED on the case law; CONTESTED on application to Law Gazelle at scale**

Germany has historically the strictest and most litigated regime among the jurisdictions surveyed, via §2 RDG's broad definition of "Rechtsdienstleistung" (legal service) and its licensing/registration requirements (§10).

- **The "own affairs" exemption**: RDG does not restrict a person handling their **own** legal matters — the Act regulates the provision of legal services **to others**. This is a clean, strong fit for **D1**: a self-represented litigant using Law Gazelle for their own custody/bankruptcy/workers'-comp matter is squarely within the own-affairs space RDG doesn't touch.
- **The wenigermiete.de / Conny line of cases (BGH VIII ZR 285/18, 2019; BGH VIII ZR 256/21, 2022)** is the key precedent for tools operated *for others*: the BGH took a **"rather generous"** reading of the debt-collection-services license (§2(2) RDG) to permit a legal-tech platform that assessed rent overcharges and pursued claims on consumers' behalf, reasoning that the activity was closely tied to a licensed debt-collection function and that RDG's purpose (protecting legal-services consumers, not shielding the profession from competition) was satisfied by the platform's registered status. Notably, the **German Bar Association criticized this outcome**, arguing consumers lose the benefit of independent professional advice — signaling ongoing professional friction even where courts have permitted the model.
- **Applied to a D2/E4 Law Gazelle deployment**: a legal-aid clinic or firm running Law Gazelle **for clients** is providing services to others, but Law Gazelle's specific function — organizing, not assessing or asserting claims — is a materially different fact pattern from wenigermiete.de's claim-assertion-on-commission model. The wenigermiete.de line establishes that German courts *can* be generous toward legal-tech business models even when RDG's literal text looks restrictive, **but that generosity was earned by a registered, licensed debt-collection status** — not a general "AI legal tool" safe harbor. **A D2/E4 deployment in Germany specifically should not assume wenigermiete.de-style protection applies by analogy without a registration/licensing analysis of its own** — this is a genuinely open question requiring German counsel, not resolved by the existence of a permissive precedent in an adjacent business model.
- **AI-specific development**: German legal-tech/bar commentary (Anwaltsblatt and others) treats "is AI a topic for RDG law" as a live, actively-discussed question as of 2025, without a settled doctrinal answer yet specific to AI-assisted tools — **flagged as UNCERTAIN and evolving**, worth monitoring rather than treating as resolved.
- **Supervisory consolidation**: as of 1 January 2025, supervision of registered legal-tech/debt-collection services was centralized at the Federal Office of Justice — a D2/E4 German deployment operating anything resembling a registered legal-service model would need to track this regulator specifically.

### 4.3 France — **Confidence: SETTLED on the statute; UNCERTAIN on application to organizing tools**

Loi n° 71-1130 (1971), Art. 54, reserves **paid, regular legal consultation and drafting of private deeds for third parties** to those holding qualifying titles (primarily avocats), subject to exceptions for other regulated professions (notaries, huissiers). This is the "monopole des avocats" / "périmètre du droit."

- **D1**: a litigant organizing their own matter is not providing consultation "to third parties" — clean fit, no exposure.
- **D2/E4**: this is where it matters. French commentary draws a distinction between **material/administrative execution** (typing, formatting, filing — permissibly outsourced to unauthorized providers) and **actual legal consultation or deed-drafting** (reserved). Law Gazelle's "drafting context, not drafted conclusions" design (assembling facts/citations/chronology for a human or supervised AI to write from, never authoring conclusions) sits closer to the permissible "material execution" side of this line than the reserved "consultation" side — but this has **not been tested against a specific French regulator or court ruling** in this research, and French legal-tech regulatory commentary specific to AI-assisted case-organization tools (as opposed to document-automation/contract-generation tools, which is where most reported French legal-tech disputes cluster) was not found. **Flagged as shallow coverage** — France is one of the jurisdictions this document could only assess at a general-statutory level, not against specific case law on point.

### 4.4 Netherlands — **Confidence: UNCERTAIN — shallow coverage, flagged honestly**

Dutch legal-services regulation is comparatively permissive and fragmented across professional bodies (advocatuur via the NOvA, notaries via Wet op het notarisambt) rather than a single UPL-style statute. Search research did not surface a Dutch equivalent of the German RDG case-law line or a specific "unauthorized legal-tech" doctrine directly on point for a tool like Law Gazelle. The Netherlands is known in the access-to-justice/legal-tech literature as one of the more permissive European jurisdictions for legal-tech innovation (rechtsbijstandverzekering — legal-expense insurance — has driven a robust non-lawyer-adjacent legal-services market), which is a directional signal but **not a substitute for actual Dutch counsel confirmation.** **This jurisdiction is one of the shallowest in this document — flagged explicitly rather than papered over.**

### 4.5 Notable outlier

No jurisdiction surveyed was found to be dramatically **more** restrictive than Germany on this specific fact pattern (organize-don't-advise tooling), and none was found to be so permissive as to create an affirmative safe harbor. Germany and England remain, as instructed, the two jurisdictions with real depth in this research; France and the Netherlands are comparatively shallow and should not be treated as cleared.

---

## 5. Legal Professional Privilege / Professional Secrecy Analogs

**Confidence: SETTLED on the doctrinal differences; this section is conceptually important because it changes what "privilege" even protects abroad.**

The US concept of attorney-client privilege (a testimonial/evidentiary privilege belonging to the client, broadly covering confidential communications for the purpose of legal advice) does **not** map cleanly onto most civil-law systems. One sentence of contrast per jurisdiction, since the user specified brevity here relative to US coverage:

- **Germany — Verschwiegenheitspflicht**: a lawyer's professional **secrecy obligation** (a duty owed by the lawyer, enforced primarily via criminal law protection against state seizure in specific circumstances) is narrower and structured differently than common-law privilege — it protects the lawyer's silence, not a client-held evidentiary privilege in the same shape, and German commentary explicitly states "Legal Privilege in Deutschland – kein umfassender Schutz" (no comprehensive protection) relative to Anglo-American expectations, meaning **data seized from a German lawyer's systems (or a client's own case-management tool) has weaker automatic protection from compelled disclosure than a US practitioner might assume.**
- **France — secret professionnel**: a criminal-law obligation of confidentiality (Penal Code) owed by the avocat, broad in coverage of information obtained in the course of the mandate, but again structured as a professional duty rather than a client-controlled evidentiary privilege — practically similar in effect to US privilege for most purposes, but doctrinally distinct in who "holds" it and how it's asserted or waived.
- **England & Wales**: legal professional privilege here is the closest analog to the US concept (same common-law lineage), covering legal advice privilege and litigation privilege, client-held and waivable by the client — the least divergence from the US model of the jurisdictions surveyed.
- **General cross-jurisdictional point relevant to Law Gazelle's architecture**: because these are largely **duties owed by the lawyer or professional**, not properties of a piece of software, **privilege/secrecy protection in every jurisdiction surveyed depends on who controls and can access the data, not on the software's design** — meaning the local-first, no-egress architecture materially *helps* every one of these regimes by minimizing the number of hands (and jurisdictions) the data passes through, but does **not by itself create or preserve privilege/secrecy** — that remains a function of the human professional relationship, not the tool. This should be stated plainly in any D2 materials: **the app helps keep privileged/secret material out of third-party hands; it is not itself a source of privilege.**
- **D1 self-represented litigants** generally have **no lawyer to hold privilege/secrecy in the first place** — most privilege/secrecy regimes surveyed are professional duties attaching to a qualified lawyer's role, not general "legal matter" confidentiality. A self-represented litigant's case data is protected (if at all) by ordinary data-protection law (§1–2) and general confidentiality/evidentiary rules, not by lawyer-client privilege — worth being precise about in any user-facing materials so as not to overstate the protection D1 users actually have.

---

## 6. Other Major Privacy Regimes

For each: the one or two obligations that actually bite, not a general statute summary.

| Jurisdiction | Statute | What actually bites for Law Gazelle | Confidence |
|---|---|---|---|
| **Canada (federal)** | PIPEDA | Applies to organizations processing personal data "in the course of commercial activity" — **a nonprofit legal-aid clinic's core service may not be "commercial activity"** in the PIPEDA sense, which could put pure-nonprofit D2 deployments partly outside PIPEDA's reach (provincial/nonprofit-specific rules may fill the gap instead) — this is a genuine, favorable-to-nonprofit distinction worth confirming with Canadian counsel rather than assuming PIPEDA applies by default the way it would to a commercial vendor. Where it does apply, PIPEDA's "sensitive information" doctrine (health data specifically named) requires heightened consent/safeguards. | SETTLED on PIPEDA's commercial-activity threshold; UNCERTAIN on how a specific nonprofit clinic's status shakes out |
| **Canada (Quebec)** | Law 25 | **Mandatory Privacy Impact Assessment before any cross-border transfer** of personal information outside Quebec (§17) — directly relevant if a Quebec-based D2 deployer ever used non-Quebec cloud AI or backup; the local-first default architecture means this PIA obligation currently has **nothing to assess** (no transfer occurs), which is a clean structural win, same logic as GDPR Chapter V (§1.10). | SETTLED |
| **Australia** | Privacy Act 1988 + Australian Privacy Principles, as amended by the Privacy and Other Legislation Amendment Act 2024 (Tranche 1, royal assent 10 Dec 2024) | (1) **New statutory tort for serious invasions of privacy** (in force by 10 June 2025) creates a direct civil cause of action relevant to any D2 breach involving custody/health data — a materially new exposure that didn't exist in Australia before this reform. (2) **New automated-decision-making transparency requirements** in privacy policies (2-year grace period to 10 December 2026) would require Law Gazelle's AI ranking/briefing features to be disclosed in any Australian D2 deployer's privacy policy once that grace period ends. **Tranche 2** of reform (broader, including a "fair and reasonable" processing test) was still pending as of this research and should be re-checked before any Australian deployment. | SETTLED on Tranche 1; UNCERTAIN on Tranche 2 timing/content |
| **Brazil** | LGPD | Health data is Art. 11 sensitive data; the **legal-claims lawful basis exists (Art. 11, "regular exercise of rights ... in judicial, administrative and arbitral proceedings")** — a clean structural parallel to GDPR Art. 9(2)(f), meaning the same architecture/reasoning largely transfers. **Legitimate interest and contract cannot be used for sensitive data under LGPD** (stricter than GDPR here) — a D2 Brazilian deployer must anchor sensitive-data processing specifically in the legal-claims (or consent, or health-protection-by-a-health-professional) ground, not a generic legitimate-interest argument. | SETTLED |
| **India** | Digital Personal Data Protection Act 2023 + DPDP Rules 2025 | Rules were notified **14 November 2025**; substantive obligations (notice, consent mechanics, security safeguards, breach reporting, data-principal rights, Significant Data Fiduciary duties) phase in with an **18-month compliance runway to 13 May 2027**. **Verifiable parental consent for anyone under 18** is a hard, bright-line requirement (India sets the age threshold at 18, not 13/16 as in GDPR) — directly relevant to any custody-matter data involving a minor: if a D2 Indian deployment ever needs to process a minor's data with the minor as a "data principal" in their own right (as opposed to only the parent-litigant's own data), DPDP's verifiable-parental-consent mechanism must be engineered for, and it is stricter than GDPR's Art. 8 (which allows a lower age threshold set by Member States, commonly 13–16). | SETTLED as of the 2025 rules notification; this is fast-moving and should be re-verified close to any actual India deployment |
| **Japan** | APPI | Requires **consent for handling "sensitive" (special-care-required) personal information** and separately requires consent before any cross-border transfer of personal data — the app's no-transfer default sidesteps the second requirement structurally; the first (consent for sensitive data) would need to be engineered into any D2 Japanese deployment's client-intake consent flow. | SETTLED |
| **South Korea** | PIPA | Classifies **biometric data used for unique identification** as a special class requiring **separate, explicit consent** distinct from general consent — not directly triggered by Law Gazelle's current data model (no biometric processing), but worth flagging if any future identity-verification feature (e.g., for E3 guided intake) introduces biometric ID checks. | SETTLED |
| **South Africa** | POPIA | "Special personal information" explicitly includes **health data and "criminal behaviour of the data subject"** as named categories (broader express inclusion of criminal-conduct data than most peer regimes) — directly relevant to both the workers'-comp (health) and custody-with-allegations (criminal-conduct-adjacent) matter types; processing is prohibited absent specific authorization grounds (consent, or legal-obligation-equivalent grounds) — structurally similar to the GDPR Art. 9/Art. 10 double-layer discussed in §1.11. | SETTLED |
| **China** | PIPL | **Extraterritorial reach is real and has been enforced against a foreign entity in a reported landmark case** (per 2024 court decision reporting) — if any Chinese resident downloads and uses Law Gazelle (D3 distribution has no way to prevent this), the **explicit-consent requirement for sensitive personal information and for any cross-border transfer** would apply to that user's own processing, not to the publisher (same D3 publisher-isn't-a-controller logic as §1.2/§8, since the publisher never receives or transfers the data). The more interesting question for the **publisher** is whether merely making the software available for download to China-based users constitutes an activity PIPL reaches — the reported case involved a company with actual operational/data-handling ties to China, a materially different fact pattern from a passive open-source GitHub repository. **Flagged as UNCERTAIN** — no authority was found directly addressing passive open-source distribution under PIPL's extraterritorial provisions. | UNCERTAIN on the passive-open-source-publisher question specifically |

---

## 7. Data Localization / Residency

**Confidence: SETTLED on the general point — this is where the local-first architecture does the most unambiguous good, with two caveats.**

Data-localization/residency mandates (found in various forms across China, India (sectorally), Russia, and others not separately surveyed above) generally require that certain categories of personal data be stored on servers physically located within the jurisdiction, or that a local copy be retained. **A purely local-first architecture with no server at all trivially satisfies any localization requirement in every jurisdiction simultaneously** — the data never leaves the user's own device, which is definitionally "local" everywhere the device happens to be.

**Where this stops helping**:
1. **If a deployer chooses cloud AI or cloud backup**, localization requirements re-engage exactly like Chapter V transfer rules (§1.10) — the moment data leaves the device, *which* server it lands on becomes legally significant again, and a D2 organization operating across multiple countries (e.g., an international access-to-justice network) would need a jurisdiction-by-jurisdiction data-residency map for any centralized backup/sync feature it might add later.
2. **MCP client location**: if an MCP client driving the app runs on infrastructure in a different country than the case data's subject-matter jurisdiction, this is a subtler point not clearly resolved by any localization statute surveyed — MCP tool calls stay local to the device running gazelle_mcp.py in the current architecture (the LLM reasoning may be remote if a cloud MCP client is used, but the case *data* itself is only ever queried locally and returned, not persisted remotely, absent an explicit export/save action) — this distinction (data queried vs. data persisted) is worth stating precisely in any deployment guide, since "an AI agent touched the data" and "the data left the device" are not the same fact, and localization law generally cares about the latter.

---

## 8. Cross-Border Issues

### 8.1 Extraterritorial reach — the D3 publisher question

**Confidence: SETTLED as a matter of the legal test; UNCERTAIN as a matter of practical enforcement exposure.**

GDPR Art. 3(2)'s targeting test (offering goods/services to, or monitoring the behavior of, EU/EEA data subjects) and PIPL's analogous extraterritorial provision are both **activity-based**, not entity-based — they ask what a specific *processing activity* does, not what the entity generally is. Applied to publishing MIT-licensed source code on GitHub:

- **Publishing code that anyone, anywhere, can download and run locally is very unlikely to itself constitute "offering a service to" EU/EEA (or Chinese) data subjects** in the Art. 3(2)/PIPL sense, **because the publisher never processes any personal data as part of that act** — there is no processing activity to which the targeting test could even attach. This is the strongest form of the D3 conclusion already stated in §1.2: **no processing, no controller/processor role, and (following from that) no meaningful targeting-test exposure**, regardless of how many EU or Chinese users happen to download the software.
- **What WOULD create exposure for a publisher**: operating any centralized service alongside the software (telemetry, crash reporting, update-check pings, an account system, a hosted demo with real data) — none of which exist in the current architecture (`local_processing: 1.0`, no account, `make demo` uses synthetic data only). **This absence should be preserved deliberately as new features are added** — it is the single fact doing the most work to keep the publisher outside every privacy regime surveyed in this document.
- **EDPB guidance caveat**: the Art. 3(2) analysis is explicitly activity-by-activity and case-by-case per EDPB Guidelines 3/2018 — this conclusion holds for the architecture *as described*, not as a permanent characteristic of "open-source software" in general; a different open-source project with telemetry would reach a different answer.

### 8.2 What publishing an MIT-licensed tool actually exposes a developer to

**Confidence: SETTLED, and this is a genuinely reassuring finding worth stating plainly.** Beyond the data-protection analysis above (which resolves to "essentially nothing, absent telemetry/accounts"), the remaining exposure categories for an MIT-licensed publisher are:

- **Product-liability-adjacent claims** (not this document's focus — a separate, non-privacy body of law, and typically weak against a free, source-available, MIT-licensed tool with explicit "information, not advice" disclaimers, but not zero — this is closer to general software/consumer-protection law than to any regime surveyed above, and MIT's own disclaimer language does real work here).
- **Unauthorized-practice-of-law exposure at the publisher level specifically (as distinct from a deployer)**: none of the UPL/RDG/reserved-activities regimes surveyed in §4 attach to a passive software publisher who neither operates the tool for clients nor holds themselves out as providing legal services — this liability consistently attaches to the **deployer/operator**, not the code author, across every jurisdiction researched.
- **AI Act GPAI/high-risk obligations**: as established in §3.5, none attach to the publisher as a matter of GPAI-provider status; if Annex III high-risk status were ever found to apply (§3.2's contested question), Art. 25's AI-Act-specific provider/deployer split would need separate analysis — **not resolved here, flagged as a downstream consequence of §3.2 rather than a separate open question.**

### 8.3 Transfer mechanisms (summary cross-reference)

Already covered substantively at §1.10 (GDPR Chapter V) and §7 (localization) — restated here only to note that **no transfer mechanism (SCCs, adequacy decisions, BCRs) is currently needed anywhere** because the default architecture makes no transfer. This becomes relevant only the moment a deployer opts into cloud AI or cloud sync — at which point the specific mechanism needed depends on the destination country and should be assessed fresh at that time, not pre-built into the current compliance posture.

---

## 9. E-Signature and E-Filing

**Confidence: SETTLED on the frameworks; LOW relevance to current Law Gazelle functionality, flagged as forward-looking.**

- **eIDAS 2.0** (Regulation (EU) 2024/1183, in force since 20 May 2024) introduces the EU Digital Identity (EUDI) Wallet, with Member States required to offer a national wallet app by end of 2026, and expands qualified trust services (e-signatures, e-seals, certified electronic archiving). **Current relevance to Law Gazelle: minimal** — the app does not currently generate, sign, or submit any court filing; it assembles "drafting context," and a human (or supervised AI, with the human verification gate) writes and files separately. **If a future feature (E3 guided intake, or any e-filing integration) began generating documents intended for direct submission with an embedded e-signature, eIDAS 2.0's qualified-signature requirements would become directly relevant** — flagged as a forward-looking trigger, not a current obligation.
- **Court e-filing regimes** vary by jurisdiction and even by court within a jurisdiction (e.g., England & Wales's CE-Filing system, various German ERV — elektronischer Rechtsverkehr — requirements which, notably, are **mandatory for lawyers** in Germany as of recent years, though not for self-represented litigants) — this document did not do a jurisdiction-by-jurisdiction e-filing survey because **Law Gazelle does not currently file anything**; this should be revisited specifically if/when an e-filing integration is scoped, not treated as covered by this document.

---

## 10. Accessibility — European Accessibility Act (EAA) and EN 301 549

**Confidence: SETTLED on the framework; CONTESTED/genuinely interesting on application to a TUI specifically.**

- **EAA scope and deadline**: covers a defined list of products/services (including "services related to transport," e-commerce, e-books, and — the closest fit — "electronic communications services" and elements of "consumer banking," but notably **the EAA's product/service list does not include general-purpose case-management or legal-aid software as such** — the enumerated categories are narrower than "any software EU consumers might use." The compliance deadline for in-scope products/services was **28 June 2025** (already passed), with a **micro-enterprise exemption (under 10 employees, under €2M turnover) for services (not products)**.
- **Is Law Gazelle in scope at all?** This is genuinely uncertain and worth stating honestly: EAA's enumerated service categories (Annex I) are oriented around consumer-facing commercial digital services (banking, e-commerce, transport, telecoms, audiovisual media, e-books) — a legal-aid case-management tool is not a clean match to any enumerated category, and **EAA generally applies to services offered commercially in the EU market**, which raises a threshold question for a free, MIT-licensed, nonprofit-posture tool distributed by a D2 legal-aid clinic rather than sold. **No authority was found squarely classifying legal-aid case-management software under EAA** — this should be confirmed with EU accessibility counsel before treating EAA as either definitely applicable or definitely inapplicable.
- **If it did apply (or as good practice regardless — recommended independent of the legal question)**: **EN 301 549's core content standard is WCAG 2.1 Level AA**, which is fundamentally a **web/GUI content standard** (color contrast, alt text, ARIA landmarks, keyboard navigation, screen-reader semantics for HTML/visual elements) — **a terminal/TUI application does not have most of the surface WCAG 2.1 targets** (no color-contrast-on-images, no alt-text-for-visual-elements in the web sense), but the **underlying accessibility principles translate directly**: (1) full keyboard operability (Textual TUIs are keyboard-native by construction — a genuine head start), (2) screen-reader compatibility, which for a terminal app means compatibility with terminal screen readers/braille displays (a nontrivial, TUI-specific engineering question Textual's framework only partially solves out of the box), (3) sufficient color contrast in the terminal color scheme (directly applicable and directly checkable), (4) no reliance on color alone to convey meaning (e.g., urgent-queue severity should not be color-only), (5) predictable, consistent navigation patterns. **Concrete engineering implication regardless of legal applicability**: run the existing TUI through a terminal screen reader (e.g., NVDA/Orca terminal-mode compatibility) as a practical proxy for EN 301 549's intent, and audit the color-only-severity-signaling question in the urgent queue specifically — this is good practice for a self-represented-litigant-facing tool independent of whether EAA technically applies.

---

## 11. Children's Data — GDPR Art. 8, National Age Thresholds, UK AADC

**Confidence: SETTLED on the frameworks; genuinely important given custody matters necessarily involve minors.**

- **GDPR Art. 8** sets the default digital-consent age at 16, but **allows Member States to lower it to as young as 13** — meaning the applicable age threshold for any "information society service" consent involving a child **varies by EU Member State** (Germany: 16; several others: 13 or 14–16 variants) — a genuinely fragmented picture across the EU that any pan-European D2 deployment would need to map country-by-country.
- **Critical scoping point for Law Gazelle specifically**: Art. 8 governs a child's own **consent** to an information-society service offered **directly to the child**. **Law Gazelle is not offered to the children involved in a custody matter** — it's the parent-litigant's tool, and the children's data is processed as part of the parent's/advocate's matter, not as a service to the child. This means **Art. 8's consent-age mechanism likely does not apply directly** to how children's data enters the app (the parent or clinic is the one whose consent/lawful-basis matters, per §1.1's Art. 9 analysis, not the child's own Art. 8 digital-consent capacity) — **but this doesn't make the children's data any less special-category-sensitive or Art. 10-adjacent** (§1.11) — it just means the *consent-age* mechanism is the wrong tool to reach for; the *special-category lawful-basis* analysis (§1.1) is the right one, and it already accounts for the children's data as part of the custody matter's overall Art. 9/Art. 10 posture.
- **UK Age Appropriate Design Code (ICO Children's Code)**: applies to "information society services" **likely to be accessed by children** — the operative test is not "does this process children's data" but "would children plausibly access/use this service directly." **Law Gazelle is not designed for, marketed to, or realistically used directly by children** — it's an adult litigant's/advocate's case-management console — so the AADC's 15 design standards (age-appropriate defaults, data minimization by design, no nudging, geolocation off by default, etc.) are aimed at services children themselves interact with, which this is not. **The AADC likely does not apply to Law Gazelle itself** for this reason, though the **children whose data appears within a custody matter remain protected by ordinary UK GDPR special-category rules** (§2), just not by the AADC's child-user-experience-specific design code. **This distinction — "processes children's data" vs. "is a service children use" — is worth stating precisely, since it's an easy point to conflate and the two trigger genuinely different obligations.**

---

## Table: Concrete Engineering / Product Implications

| # | Requirement | DO / STORE / DISPLAY / LOG / REFUSE | Triggering deployment model | Source |
|---|---|---|---|---|
| 1 | Add a persistent, visible "AI-generated — verify before relying on this" label on every AI briefing/ranking/draft-context surface | **DISPLAY** | All (D1/D2/D3), but the obligation attaches at deployer level | EU AI Act Art. 50 (§3.4) — live obligation now |
| 2 | Produce an Art. 30-style processing-record export (data subjects, categories incl. special-category flags, purposes, retention, recipients=none-by-default) derivable from `safe-app-manifest.json`'s `data_streams` block, reshaped for a *deploying organization's* client data rather than the app's own operational state | **STORE / DISPLAY (on demand)** | D2 | GDPR Art. 30 (§1.3) |
| 3 | Be able to produce a DPIA-ready description of processing, risks, and mitigations (much of the content already exists in the app's own design docs) before any D2 pilot goes live | **PRODUCE on demand** | D2 | GDPR Art. 35 (§1.4) |
| 4 | Document, in any D2 deployment guide, that erasure/rectification requests reaching case-relevant data must be fulfilled at the **Nest layer**, not inside Law Gazelle — the app cannot itself erase canonical data by design | **DISCLOSE (in deployment docs)** | D2 | GDPR Art. 17/16 (§1.7) |
| 5 | Build a DSAR-export tool (query all three stores — Nest copy, sidecar, AI cache — for a given data subject) | **DO (build)** | D2 | GDPR Art. 15 (§1.7) — low-effort relative to typical SaaS DSAR problem given local SQLite |
| 6 | Make the WillowGate audit ledger **mandatory, not optional**, for any D2/E4 deployment — it is currently the only mechanism that could start a 72-hour breach-notification clock, and off-by-default is not viable once client data is involved | **LOG** | D2/E4 | GDPR Art. 33/34 (§1.8); also AI Act Art. 12/14 if high-risk status is ever confirmed (§3.3) |
| 7 | Keep the `_fact_blocked` human-verification gate load-bearing for every future AI feature, not just current ones — this is what currently keeps Art. 22 (EU) and AI Act Art. 14 human-oversight analysis on the safe side | **REFUSE** (drafting/decisions without human verification) | All, but especially D2/E4 | GDPR Art. 22 (§1.9); AI Act Art. 14 (§3.3) |
| 8 | Do not add telemetry, crash reporting, update-ping, or account infrastructure without re-running the entire §1.2/§8.1 "publisher is not a controller" analysis — that absence is the single fact doing the most cross-jurisdictional protective work in this document | **REFUSE** (by omission) | D3 (publisher) | GDPR Art. 3(2)/Art. 4(2) (§1.2, §8.1); PIPL extraterritorial scope (§6) |
| 9 | For any Member State (or non-EU jurisdiction) deployment touching custody matters with abuse/domestic-violence allegations, confirm the Art. 10 (or POPIA-equivalent "criminal behaviour") lawful basis with local counsel before go-live — this is Member-State/jurisdiction-specific and not resolved generally | **PRODUCE (legal basis memo) before go-live** | D2, custody matters specifically | GDPR Art. 10 (§1.11); POPIA (§6) |
| 10 | For any Germany-specific D2/E4 deployment, obtain a fresh RDG analysis specific to Law Gazelle's actual feature set — do not rely on wenigermiete.de by analogy | **PRODUCE (legal opinion) before go-live** | D2/E4, Germany | RDG case law (§4.2) |
| 11 | For India deployments involving a minor as an independent data principal (not just as data within the parent's matter), engineer verifiable parental consent per DPDP Rules 2025 | **DO / STORE (consent record)** | D2, India, if applicable | DPDP Act 2023 + Rules 2025 (§6) |
| 12 | Before any EU AI Act high-risk conformity work is undertaken, re-confirm the §3.2 classification with counsel — the December 2027 deadline gives runway, but the question should not be left unresolved indefinitely, especially before E3/E4 | **PRODUCE (classification memo)** | D2/E4, EU | AI Act Annex III (§3.2) |
| 13 | Audit the TUI's color-only severity signaling (urgent queue) and test with a terminal screen reader as a proxy for EN 301 549 intent | **DO (audit)** | All, good practice | EAA/EN 301 549 (§10) |
| 14 | Do not describe D1 users as protected by "attorney-client privilege" or its exact equivalent in any non-US jurisdiction — most self-represented D1 users have no lawyer to hold privilege/secrecy in the first place; be precise that the app protects data *custody*, not legal *privilege* | **DISPLAY (accurate user-facing language)** | D1 primarily | §5 |
| 15 | Flag prominently to any D2 deployer that switching on cloud AI or cloud backup re-engages GDPR Chapter V, Quebec Law 25 §17 PIA, and data-localization analysis that the default local-first config avoids entirely | **DISCLOSE (in deployment docs)** | D2 | §1.10, §6, §7 |

---

## Jurisdiction Quick-Reference Table

| Jurisdiction | Primary regime(s) | Sharpest exposure for Law Gazelle | Depth of this research |
|---|---|---|---|
| EU/EEA | GDPR | Art. 9 special-category lawful basis at D2 scale; DPIA trigger | Deep |
| EU | AI Act (as amended by Digital Omnibus) | Annex III high-risk classification question (CONTESTED); Art. 50 transparency (live now) | Deep |
| UK | UK GDPR + DPA 2018 + Data (Use and Access) Act 2025 | Same as EU, minor 2025-reform divergences | Deep |
| Germany | RDG | Unauthorized-legal-services risk at D2/E4 scale; wenigermiete.de line doesn't auto-apply | Deep |
| England & Wales | Legal Services Act 2007 | Narrow statutory exposure; SRA policy-attention risk | Deep |
| France | Loi 71-1130 | Consultation/deed-drafting monopole; organizing-vs-advising line untested here | Shallow |
| Netherlands | Fragmented professional regulation | No clear UPL-equivalent found on point | Shallow |
| Canada (federal) | PIPEDA | Commercial-activity threshold may exclude pure nonprofits | Moderate |
| Canada (Quebec) | Law 25 | Mandatory PIA before any cross-border transfer | Moderate |
| Australia | Privacy Act 1988 (Tranche 1 reform) | New statutory privacy tort; ADM disclosure (2026 grace period) | Moderate |
| Brazil | LGPD | Legal-claims basis parallels GDPR 9(2)(f); no legitimate-interest for sensitive data | Moderate |
| India | DPDP Act 2023 + Rules 2025 | Verifiable parental consent under-18; phased compliance to May 2027 | Moderate |
| Japan | APPI | Consent for sensitive data and for any cross-border transfer | Shallow-moderate |
| South Korea | PIPA | Biometric-specific consent (not currently triggered) | Shallow |
| South Africa | POPIA | Explicit inclusion of "criminal behaviour" as special category | Shallow-moderate |
| China | PIPL | Extraterritorial reach real but untested against passive OSS publishing | Shallow, explicitly uncertain |
| eIDAS/e-filing | eIDAS 2.0 | Not currently triggered; forward-looking only | Shallow (low relevance today) |
| EAA/EN 301 549 | Accessibility | Threshold applicability itself uncertain for this service type | Moderate, genuinely uncertain |

---

## Open Questions Requiring Actual Counsel

1. **Germany**: does Law Gazelle's specific feature set (organize/draft-context, never assess/assert) require RDG registration at D2/E4 scale, or does it stay within the own-affairs/material-execution space? Needs German counsel, ideally with the wenigermiete.de/Conny reasoning tested against this exact fact pattern.
2. **EU AI Act**: is the §3.2 "not high-risk" conclusion durable once a named pilot partner and specific E3/E4 features are locked in? Needs counsel before any conformity-relevant commitment is made to a partner org — the December 2027 deadline gives time but shouldn't become an excuse to leave this unresolved.
3. **GDPR Art. 2(2)(c)**: does the household exemption actually cover D1 given the presence of third parties (co-parent, children, employer, insurer) in the data? No case law found squarely on point (§1.5) — worth a formal opinion if D1 messaging will ever assert GDPR-exemption status affirmatively rather than simply relying on the architecture's low-risk profile regardless.
4. **France and Netherlands**: both flagged as shallow in this research. Before any deployment in either country, commission jurisdiction-specific counsel review — this document should not be read as having cleared either.
5. **China (PIPL)**: does passive open-source distribution via a public GitHub repository, without any operational nexus to China, actually trigger PIPL's extraterritorial provisions? No authority found directly on point; likely low risk given the D3 publisher analysis (§8.1), but "likely low risk" is not the same as "cleared."
6. **EAA/EN 301 549 applicability**: does a free, MIT-licensed, nonprofit-posture legal-aid tool fall within EAA's enumerated service categories at all? Threshold question not resolved here (§10) — worth a specific opinion before treating EAA as either a compliance target or a non-issue.
7. **Member-State-specific Art. 9(2)(g)/Art. 10 authorizations**: several EU Member States have specific statutory bases for legal-aid bodies processing sensitive/criminal-adjacent data — not surveyed country-by-country here (§1.1, §1.11); needed before any specific Member State D2 pilot.
8. **India**: DPDP Rules were only notified 14 November 2025 and substantive obligations phase in through May 2027 — this is genuinely live-moving law; re-verify current status immediately before any India-facing decision rather than relying on this document's snapshot.
9. **Australia Tranche 2** privacy reform content and timing was not confirmed in this research as finalized — re-check before any Australian deployment.

---

*Prepared 2026-08-04 by automated research (WebSearch/WebFetch against primary and secondary sources) for internal engineering/product planning. Not a substitute for jurisdiction-specific legal counsel. See disclaimer at top.*
