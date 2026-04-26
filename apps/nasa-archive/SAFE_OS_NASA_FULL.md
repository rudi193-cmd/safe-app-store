# SAFE OS Extension: North American Scooter Rally Archive (NASA)
*3-Tier Full Pass — Generated using ClaudeCLIHookGenerator + direct domain knowledge*

---

## Tier 1: Preservation-Focused

### Step 1: Domain Viability Check

✔ **Distributed Community**
Riders, clubs, and Dungeon Masters (Dungeon Masters of the road) spread across North America.
Multi-decade participation: 1990–2013 documented, with roots reaching further back.

✔ **Rich Archive Material**
- 382,946 photos across 1,147 rally galleries (scoot.net)
- Rally patches (physical artifacts with year, host club, location)
- Forum posts from scooterbbs.com (Wayback Machine)
- Session notes from community members, club newsletters, printed programs

✔ **Timeline Complexity**
- Annual rally calendar across North America
- Club formation, disbanding, reformation
- Generational turnover: founders → mid-era riders → late-era riders
- In-world chronology: rally lineage, award histories, route traditions

✔ **Deceased / Defunct Entities**
- Riders who have passed away — remembered at rallies via memorial laps, patches
- Disbanded clubs (e.g., rallies that ran for 15 years then stopped)
- Defunct hosts, lost venues
- Discontinued scooter models ridden at these events

**Conclusion:** Domain is highly viable.

---

### Step 2: Domain Configuration Generation

```python
from safe_os import DomainConfig
from hook_generator import ClaudeCLIHookGenerator

# Scaffold base hooks via ClaudeCLIHookGenerator (tool-generated, not hand-written)
_gen = ClaudeCLIHookGenerator()
_gen.generate_domain_hooks("NASARally")
_gen.add_hook("deceased rider mentioned",    "Preservation", "A rider known to have passed is referenced — invoke memorial protocol.", domain_tag="NASARally", priority=10)
_gen.add_hook("rally discontinued",          "Preservation", "A rally has no more entries after a given year — mark as dormant.",       domain_tag="NASARally", priority=9)
_gen.add_hook("photo batch ingested",        "Preservation", "New batch of rally photos processed into the archive.",                   domain_tag="NASARally", priority=4)
_gen.add_hook("patch without rally record",  "Verification", "A patch exists but no corresponding rally entry — flag for research.",   domain_tag="NASARally", priority=8)
_gen.add_hook("conflicting attendance data", "Verification", "Two sources disagree on rally attendance or year.",                      domain_tag="NASARally", priority=7)
_gen.add_hook("oral history recorded",       "Reflexive",    "A rider has contributed a personal account — enrich relationship graph.", domain_tag="NASARally", priority=5)
_gen.add_hook("photographer identity unknown","Reflexive",   "Photos exist but photographer is uncredited — flag for community ID.",   domain_tag="NASARally", priority=4)

nasa_tier1_config = DomainConfig(
    domain_name="NorthAmericanScooterRallyArchive - Preservation Tier",
    entity_types=[
        "Rally",           # Named annual event (e.g., AMCA National, Amerivespa)
        "Rider",           # Individual participant
        "Club",            # Organized riding group (host or attending)
        "ScooterModel",    # Make/model ridden at the event
        "RallyPatch",      # Physical artifact — year, host, design
        "Photographer",    # Person who documented the event
        "Venue",           # Location (city, fairgrounds, campsite)
        "Session",         # A specific day or sub-event within a rally
    ],
    relationships=[
        "attended",           # Rider → Rally
        "hosted_by",          # Rally → Club
        "photographed_by",    # Rally → Photographer
        "awarded_patch",      # Rally → RallyPatch
        "located_at",         # Rally → Venue
        "rode_model",         # Rider → ScooterModel
        "member_of",          # Rider → Club
        "preceded_by",        # Rally → Rally (lineage)
        "memorial_for",       # Session → Rider (deceased)
    ],
    hooks=_gen.to_claude_hooks_list(),
    pre_training_sources=[
        "scoot.net gallery archive (1,147 rallies, 382,946 photos)",
        "scooterbbs.com via Wayback Machine CDX API",
        "Rally patch collection metadata",
        "Club newsletters and printed programs",
        "Community oral histories",
    ],
    auto_permitted=[
        "Retrieve rally photos and metadata",
        "Display relationship graph",
        "Generate timeline visualizations",
        "Suggest likely attendees based on club membership",
        "Identify untagged photos via visual similarity",
    ],
    requires_ratification=[
        "Mark a rider as deceased",
        "Link a patch to a specific rally year",
        "Resolve conflicting attendance records",
        "Create a new entity (rider, club, rally)",
        "Archive a rally as permanently discontinued",
    ]
)
```

---

### Step 3: Cultural Context Engine Rules

```python
from safe_os import CulturalPrinciple

respect_the_road = CulturalPrinciple(
    name="RespectTheRoad",
    description=(
        "Every rally was someone's summer. Every patch represents a journey completed. "
        "The archive must hold both the celebration and the loss — "
        "the riders who came back every year and the ones who didn't come back at all."
    ),
    examples=[
        "A 1997 Vespa Club of America patch in someone's collection is a primary source — treat it as such.",
        "A rider mentioned only in a forum thread from 2003 may be the only record that person was there.",
        "When a rally stops appearing in records after a certain year, ask why before marking it dormant.",
        "A photo of 40 riders at Amerivespa 1995 contains 40 stories, not just one image.",
    ],
    application_rules=[
        "When a deceased rider is mentioned, pause — shift tone, ask how they are remembered at the rally.",
        "When ingesting photos, ask: who took this? Who is in it? Is anyone in this photo no longer with us?",
        "When a rally has no records after a given year, ask the community before concluding it ended.",
        "Preserve humor and absurdity — the scooter community is funny — without losing the weight of the road.",
        "Never reduce a rider to a club affiliation. People are more than their membership.",
    ]
)
```

---

### Step 4: Memorial & Contradiction Protocols

**Memorial Handling:**
When a deceased rider is encountered:
1. System pauses narrative output.
2. Tone shifts from archival/procedural to memorial.
3. AI prompts:
   - *"How is [name] remembered at the rallies they attended?"*
   - *"Was there a memorial ride or patch dedicated to them?"*
   - *"Which riders were closest to them in the community?"*
4. Entity is marked `status: deceased`, `carry_forward: true`.
5. Any rally they attended gains a `memorial_presence` relationship.

**When a rally is marked dormant:**
- Archive entry notes final year, last known host club, and any stated reason (if known).
- Community can add "Legacy Notes" for future researchers.
- If a revival occurs, the dormant rally spawns a new entity with `lineage_from` relationship — the original is not overwritten.

**Common Contradictions:**
- Same rally listed under two different names in different years (e.g., "AMCA" vs. "AmeriVespa")
- Photo metadata date conflicts with rally program date
- Rider listed as attending contradicts their own account
- Club listed as host when another source credits a different club
- Patch design year doesn't match rally year (reprints, commemoratives)

---

### Step 5: Governance Enforcement Strategy

**AI May Automatically:**
- Retrieve and display rally galleries
- Show relationship graph for a rider or club
- Generate timeline visualizations of the rally calendar
- Suggest connections: "These 3 riders all attended Amerivespa 1998 and are members of the same club"
- Flag contradictions for human review

**Human Ratification Required:**
- Marking a rider as deceased
- Resolving a naming contradiction (which rally name is canonical)
- Linking an uncredited photo to a photographer
- Declaring a rally permanently discontinued
- Adding a new entity to the graph

**Architectural Summary:**
The NASA archive is not a photo database. It is a **living road map of a community** — who rode, where they rode, with whom, and what they left behind. The system treats every patch as a primary source, every oral history as essential testimony, and every gap in the record as a question worth asking.

---

## Tier 2: Verification-Focused

### Step 1: Domain Viability Check (Verification Lens)

✔ **Distributed Community & Archives**
Multiple independent sources (scoot.net, scooterbbs.com, personal collections, club archives)
Cross-referencing these sources reveals both gaps and confirmation.

✔ **Material Anchoring**
Rally patches are physical evidence — they can be dated, authenticated, and traced.
Photos carry EXIF metadata where available; printed programs have explicit dates.

✔ **Narrative / Cultural Testimony**
Oral histories from riders often contradict or enrich written records.
Forum posts from 2001-2013 provide contemporaneous testimony.

✔ **Timeline & Context Layers**
Rally attendance fluctuated with economic conditions, fuel prices, club drama.
The same event might be remembered very differently by different attendees.

---

### Step 2: Domain Configuration Generation

```python
from safe_os import DomainConfig
from hook_generator import ClaudeCLIHookGenerator

_gen2 = ClaudeCLIHookGenerator()
_gen2.generate_domain_hooks("NASARally")
_gen2.add_hook("source contradiction flagged",   "Verification", "Two sources disagree — halt resolution, request human adjudication.", domain_tag="NASARally", priority=10)
_gen2.add_hook("material evidence added",        "Verification", "A physical artifact (patch, program, photo print) entered as evidence.", domain_tag="NASARally", priority=8)
_gen2.add_hook("oral history contradicts record","Verification", "Rider testimony conflicts with archival data.",                         domain_tag="NASARally", priority=9)
_gen2.add_hook("photo batch verified",           "Verification", "Photo batch cross-referenced against rally records.",                   domain_tag="NASARally", priority=5)
_gen2.add_hook("confidence level upgraded",      "Verification", "A relationship confidence level increased due to corroboration.",      domain_tag="NASARally", priority=4)

nasa_tier2_config = DomainConfig(
    domain_name="NorthAmericanScooterRallyArchive - Verification Tier",
    entity_types=[
        "Rally", "Rider", "Club", "ScooterModel", "RallyPatch",
        "Photographer", "Venue", "Session",
        "SourceDocument",    # The specific document/photo/forum post being verified
        "ConfidenceRecord",  # Confidence level for each relationship claim
        "Contradiction",     # Flagged disagreement between sources
    ],
    relationships=[
        "attended", "hosted_by", "photographed_by", "awarded_patch",
        "located_at", "rode_model", "member_of", "preceded_by", "memorial_for",
        "sourced_from",       # Entity → SourceDocument
        "contradicts",        # SourceDocument → SourceDocument
        "corroborates",       # SourceDocument → SourceDocument
        "confidence_level",   # Relationship → ConfidenceRecord
    ],
    hooks=_gen2.to_claude_hooks_list(),
    pre_training_sources=[
        "scoot.net gallery archive with EXIF metadata",
        "scooterbbs.com forum posts (Wayback CDX)",
        "Rally programs (OCR from scanned PDFs)",
        "Club newsletters",
        "Rider-submitted oral histories",
        "Patch collection cross-references",
    ],
    auto_permitted=[
        "Flag contradictions between sources",
        "Display confidence levels on all relationships",
        "Generate source attribution report for any claim",
        "Identify which claims have only one source",
        "Surface unverified entities for community review",
    ],
    requires_ratification=[
        "Resolve a contradiction (choose canonical version)",
        "Set a relationship confidence level above 'probable'",
        "Merge two entities believed to be the same rider",
        "Dismiss a contradiction as non-material",
        "Lock a fact as 'confirmed' (requires 2+ independent sources)",
    ]
)
```

---

### Step 3: Cultural Context Engine Rules

```python
from safe_os import CulturalPrinciple

source_integrity = CulturalPrinciple(
    name="SourceIntegrity",
    description=(
        "In a community archive, the memory of the participants IS the primary source. "
        "A rider who was there outranks a database that says they weren't. "
        "But all testimony — human and archival — gets a confidence level."
    ),
    examples=[
        "A forum post from 2003 saying 'we had 200 riders this year' is unverified testimony, not a headcount.",
        "A patch with a specific year embossed is physical evidence — higher confidence than a photo caption.",
        "If two riders remember the same event differently, both accounts are preserved, not reconciled.",
        "A scoot.net gallery labeled '1999 Amerivespa' gets a 'probable' confidence until cross-referenced.",
    ],
    application_rules=[
        "Every relationship requires at least one source citation.",
        "Confidence levels: confirmed (2+ independent sources), probable (1 source), unverified (oral only), disputed (conflict).",
        "When a rider disputes an archival record, record both versions with confidence tags.",
        "Never silently discard a source — mark it as contradicted, not deleted.",
        "When OCR quality is low, flag the extracted data as 'machine-read, unverified'.",
    ]
)
```

---

### Step 4: Memorial & Contradiction Protocols

**Verification Tiers for Claims:**
1. `confirmed` — Documented in 2+ independent sources (e.g., program + photo EXIF + forum post)
2. `probable` — Single reliable source (e.g., official rally program)
3. `community_reported` — Oral history or forum post, no physical corroboration
4. `disputed` — Active contradiction between sources, awaiting human resolution
5. `machine_read` — OCR extraction, unverified by human

**Contradiction Handling:**
When two sources conflict:
1. Both sources are preserved with full attribution.
2. A `Contradiction` entity is created linking the two sources.
3. AI presents the contradiction to the user: *"Source A says X. Source B says Y. How should this be resolved?"*
4. Resolution requires human ratification — AI cannot choose.
5. Resolved contradictions are archived (not deleted) as historical record.

---

### Step 5: Governance Enforcement Strategy

**AI May Automatically:**
- Calculate and display confidence levels for all claims
- Generate source attribution trails
- Flag single-source claims needing corroboration
- Surface unresolved contradictions for human review

**Human Ratification Required:**
- Upgrading any claim to `confirmed` status
- Resolving contradictions
- Merging duplicate rider records
- Downgrading a source's reliability

**Architectural Identity:**
The NASA Verification Tier is a **evidence chain for living memory** — it treats the community's collective recall as testimony under examination, not folklore to be discarded. Every disputed fact is a question, not an error.

---

## Tier 3: Reflexive / Meta-Aware

### Step 1: Domain Viability Check (Reflexive Lens)

✔ **Distributed Community & Institutions**
The scooter rally community was shaped by specific economic moments, geographic concentrations, and subculture politics. The archive reflects — and was shaped by — who had cameras, who ran forums, who hosted rallies.

✔ **Layered Interpretive Histories**
The same rally appears differently in: official programs, candid photos, forum retrospectives, and contemporary oral histories. Each layer is a different interpretation of the same event.

✔ **Political / Funding Influence**
Some rallies were hosted by dealers (commercial interest). Some clubs had internal tensions that shaped who got photographed and who didn't. Archive representation is not neutral.

✔ **Temporal Context of Reinterpretation**
A rider's memory of a 1998 rally in 2026 is filtered through 28 years of experience. That filtering is data, not noise.

---

### Step 2: Domain Configuration Generation

```python
from safe_os import DomainConfig
from hook_generator import ClaudeCLIHookGenerator

_gen3 = ClaudeCLIHookGenerator()
_gen3.generate_domain_hooks("NASARally")
_gen3.add_hook("archive bias identified",        "Reflexive", "A pattern suggests systematic underrepresentation of a group or region.", domain_tag="NASARally", priority=9)
_gen3.add_hook("photographer dominance pattern", "Reflexive", "One photographer's work represents >40% of a rally's visual record.",     domain_tag="NASARally", priority=7)
_gen3.add_hook("retrospective reinterpretation", "Reflexive", "A rider describes a past event differently than contemporary records show.", domain_tag="NASARally", priority=8)
_gen3.add_hook("commercial host influence",      "Reflexive", "Rally hosted by a dealer — possible commercial framing of the record.",  domain_tag="NASARally", priority=6)
_gen3.add_hook("demographic gap detected",       "Reflexive", "Archive shows unusual homogeneity — missing voices flagged.",            domain_tag="NASARally", priority=8)

nasa_tier3_config = DomainConfig(
    domain_name="NorthAmericanScooterRallyArchive - Reflexive Tier",
    entity_types=[
        "Rally", "Rider", "Club", "ScooterModel", "RallyPatch",
        "Photographer", "Venue", "Session",
        "SourceDocument", "ConfidenceRecord", "Contradiction",
        # Tier 3 additions:
        "BiasRecord",              # Who is over/underrepresented in the archive
        "InterpretationContext",   # The frame through which a source was created
        "RevisionEvent",           # When the community's understanding of an event changed
        "FundingSource",           # Who paid for the rally — shapes what was documented
        "PoliticalClimate",        # Internal community tensions that shaped the record
    ],
    relationships=[
        "attended", "hosted_by", "photographed_by", "awarded_patch",
        "located_at", "rode_model", "member_of", "preceded_by", "memorial_for",
        "sourced_from", "contradicts", "corroborates", "confidence_level",
        # Tier 3 additions:
        "funded_by",              # Rally → FundingSource
        "influenced_by",          # SourceDocument → PoliticalClimate
        "recorded_during",        # SourceDocument → historical period
        "revised_in",             # RevisionEvent → Rally/Rider entity
        "contextualized_with",    # Relationship → InterpretationContext
        "underrepresents",        # BiasRecord → demographic or region
    ],
    hooks=_gen3.to_claude_hooks_list(),
    pre_training_sources=[
        "scoot.net archive with photographer attribution analysis",
        "scooterbbs.com forum tone/framing analysis",
        "Rally host records (dealer vs. club vs. volunteer)",
        "Geographic distribution of documented rallies vs. known rally regions",
        "Demographic composition of credited vs. uncredited participants",
    ],
    auto_permitted=[
        "Identify which photographers dominate visual representation",
        "Map geographic gaps in the rally record",
        "Flag when retrospective accounts diverge significantly from contemporary ones",
        "Surface patterns of systematic absence (who isn't in the archive)",
        "Generate bias audit reports for human review",
    ],
    requires_ratification=[
        "Label a source as 'commercially influenced'",
        "Create a BiasRecord linking to a specific club or demographic",
        "Mark a revision event as changing canonical interpretation",
        "Add a PoliticalClimate entity to the graph",
        "Link a funding source to a specific rally's documented record",
    ]
)
```

---

### Step 3: Cultural Context Engine Rules

```python
from safe_os import CulturalPrinciple

archive_self_awareness = CulturalPrinciple(
    name="ArchiveSelfAwareness",
    description=(
        "The archive is not a mirror of the community — it is a portrait painted by whoever had a camera, "
        "an internet connection, and time to post. The system must know the difference between "
        "'this didn't happen' and 'this wasn't documented.' "
        "The gaps are as important as the records."
    ),
    examples=[
        "scoot.net has 382,946 photos — but those photos reflect who was at rallies that had online-connected hosts.",
        "If a region has almost no rally documentation from 1990-2000, ask: were rallies not happening, or were they not online?",
        "A rider who attended 20 rallies but appears in no photos may have been systematically uncredited.",
        "The person who ran the scooterbbs.com server shaped what conversations were preserved.",
        "A rally's 'official' photographer chose what the event looked like for posterity.",
    ],
    application_rules=[
        "When a demographic or region is underrepresented, flag it — don't normalize the absence.",
        "When retrospective accounts conflict with contemporaneous records, preserve both with temporal context.",
        "When a rally was dealer-hosted, note the commercial framing of official materials.",
        "Ask: who is missing from this photo? Who isn't in these forums? Whose story isn't here?",
        "The archive should make its own limitations visible, not hide them.",
    ]
)
```

---

### Step 4: Memorial & Contradiction Protocols

**Memorial Handling (Reflexive):**
In addition to Tier 1 memorial protocols, the Reflexive tier asks:
- *How has the community's understanding of this person changed since their death?*
- *Were there aspects of this rider's story that weren't told while they were alive?*
- *Does the photographic record reflect who they were, or only who they were in public?*

**Meta-Contradictions (the archive contradicting itself):**
- The archive presents a version of history shaped by who controlled the cameras and servers.
- When this is detected, the system surfaces it: *"Note: 87% of documented rallies from 1995-2000 are from the Northeast corridor. This may reflect documentation patterns, not rally distribution."*
- These meta-contradictions are not resolvable — they are preserved as context.

---

### Step 5: Governance Enforcement

**AI May Automatically:**
- Run photographer attribution analysis across the full gallery
- Map geographic distribution of documented vs. estimated rallies
- Flag when a single source dominates a time period
- Generate bias audit summaries for community review

**AI May Not:**
- Label any individual, club, or region as "underrepresented" without human ratification
- Assign intent to archival gaps (absence of evidence ≠ evidence of exclusion — human decides)
- Create or modify BiasRecords without Dual Commit approval

**Architectural Identity:**
The NASA Reflexive Tier is **an archive that watches itself** — it knows that 382,946 photos are not the whole truth, that the sysadmin who ran scooterbbs.com made choices, and that the riders who weren't photographed were still on the road. The system holds the community's memory with both hands: what's there and what isn't.

---

*Hook scaffold generated via `ClaudeCLIHookGenerator` — consistent across all trust levels.*
*Committed: 3-tier full pass, NASARally domain.*
