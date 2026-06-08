"""
client_profile.py — Law Gazelle
b17: 880CL
================================
Loads persona.md and extracts the facts the Gazelle needs at session start.

Usage:
    from client_profile import build_context
    context = build_context()
    session = create_session("Client", context=context)

The context dict matches the shape expected by gazelle_engine.create_session():
    {
        "facts": list[str],          # plain-English fact strings
        "source_files": list[str],   # provenance
    }
"""

from pathlib import Path

# Canonical persona.md location — lives at the system level, not in the repo.
_PERSONA_PATH = Path.home() / "persona.md"
_FALLBACK_PATH = Path(__file__).parent / "data" / "client" / "persona.md"


def _load_persona_md() -> str:
    for p in (_PERSONA_PATH, _FALLBACK_PATH):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def build_context() -> dict:
    """
    Return a context dict for create_session() pre-loaded with facts from persona.md.

    Facts are curated for legal relevance — the Gazelle doesn't need the
    client's full life history. It needs: who the client is, what the case is,
    the injury, the deadlines, the jurisdiction.
    """
    persona = _load_persona_md()
    source = str(_PERSONA_PATH) if _PERSONA_PATH.exists() else str(_FALLBACK_PATH)

    # Static facts derived from persona.md (as of 2026-03-31, b17: HE50K).
    # These are example/synthetic facts — update here when the client profile changes.
    facts = [
        "Client: Example Client, Example City, ST.",
        "Case: WCA No. 00-00000, Doe v. Example Employer Inc., "
        "State Workers' Compensation Administration.",
        "Injury: Work-related back injury during employment at Example Employer.",
        "Medical: Treatment ongoing; currently on medical leave.",
        "Employment: Long-term employee at Example Employer; currently on medical leave.",
        "Mediation: Mediation case 00-00000 scheduled (see correspondence files).",
        "Financial context: Chapter 13 bankruptcy active (case 00-00000-x00, ST). "
        "Foreclosure proceedings underway.",
        "Legal representative for disability issues: Ada (AI research agent). "
        "Workers comp attorney engaged.",
        "Jurisdiction: Example State. Governing statute: the State Workers' Compensation Act.",
        "Primary input: voice-to-text. Correct transcription errors silently.",
    ]

    # If persona.md is available, also note that it's loaded so the Gazelle
    # can reference it for any additional context without re-parsing here.
    if persona:
        facts.append(f"Full persona on file at {source} — additional context available on request.")

    return {
        "facts": facts,
        "source_files": [source],
    }


def get_client_name() -> str:
    return "Client"


if __name__ == "__main__":
    ctx = build_context()
    print(f"Loaded {len(ctx['facts'])} facts from {ctx['source_files'][0]}")
    for f in ctx["facts"]:
        print(f"  • {f}")
