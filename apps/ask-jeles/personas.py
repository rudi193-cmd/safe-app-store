"""
AskJeles Personas
=================

The canonical Jeles persona lives in the `jeles` organ — one JSON source of
truth, compiled deterministically into a system-prompt string. This module no
longer carries its own hand-authored copy (the #18 combine): it renders from
`jeles.persona_prompt()`. Every distinctive beat of the old prose (misfiled,
the bifurcated vision, the Giles Coefficient, the Binder, the product role, the
"wrong drawer" line, the courses) was folded into the canonical JSON, so the
compiled prompt is a superset of what used to live here.
"""
from jeles import persona_prompt

PERSONAS = {
    "Jeles": persona_prompt(),
}


def get_persona(name: str) -> str:
    """Get a persona prompt by name. Returns Jeles default if not found."""
    return PERSONAS.get(name, PERSONAS["Jeles"])
