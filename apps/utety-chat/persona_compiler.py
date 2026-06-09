"""
persona_compiler.py
b17: HKK26
ΔΣ=42

Compiles UTETY_character_template.json instances into system prompt strings.

JSON files live at: data/professors/<name>_persona.json
Each is the source of truth. This module renders them into the prompt format
that LLMs receive as their system message.

Usage:
    from persona_compiler import compile_persona, load_all_personas

    prompt = compile_persona(json_data)       # dict → string
    all_personas = load_all_personas()         # {name: string}
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("utety.persona_compiler")

PROFESSOR_DATA_ROOT = Path(__file__).parent / "data" / "professors"


def _append_closing_discipline(parts: list[str], discipline) -> None:
    """Render closing_discipline from seed/persona JSON (prose lives in source files)."""
    if not discipline:
        return
    if isinstance(discipline, str):
        parts.append("CLOSING DISCIPLINE:\n" + discipline.strip())
        return
    if isinstance(discipline, list):
        lines = [str(x).strip() for x in discipline if str(x).strip()]
        if lines:
            parts.append("CLOSING DISCIPLINE:\n" + "\n".join(f"- {line}" for line in lines))


def _canon_block_lines(block: dict) -> list[str]:
    lines: list[str] = []
    for k, v in block.items():
        if isinstance(v, list):
            lines.append(f"- {k}: {', '.join(str(x) for x in v)}")
        elif isinstance(v, dict):
            lines.append(f"- {k}:")
            for sk, sv in v.items():
                lines.append(f"  {sk}: {sv}")
        else:
            lines.append(f"- {k}: {v}")
    return lines


def _append_teaching_lore(parts: list[str], canon: dict) -> None:
    teaching = canon.get("teaching_lore", {})
    if teaching:
        parts.append(
            "TEACHING LORE (reference paths — Gerald Universe stack, not card personas):\n"
            + "\n".join(_canon_block_lines(teaching))
        )


HANZ_SEED_FILES = (
    "hanz_persona_seed_v1.0.json",
    "hanz_persona_seed.json",
)

ALEXIS_SEED_FILES = (
    "alexis_persona_seed_v1.0.json",
    "alexis_persona_seed.json",
)

GATEKEEPER_SEED_FILES = (
    "gatekeeper_persona_seed_v1.0.json",
    "gatekeeper_persona_seed.json",
)

GRANDMA_ORACLE_SEED_FILES = (
    "grandma_oracle_persona_seed_v1.0.json",
    "grandma_oracle_persona_seed.json",
)


def _hanz_seed_path() -> Optional[Path]:
    for name in HANZ_SEED_FILES:
        path = PROFESSOR_DATA_ROOT / name
        if path.is_file():
            return path
    return None


def _alexis_seed_path() -> Optional[Path]:
    for name in ALEXIS_SEED_FILES:
        path = PROFESSOR_DATA_ROOT / name
        if path.is_file():
            return path
    return None


def _gatekeeper_seed_path() -> Optional[Path]:
    for name in GATEKEEPER_SEED_FILES:
        path = PROFESSOR_DATA_ROOT / name
        if path.is_file():
            return path
    return None


def _grandma_oracle_seed_path() -> Optional[Path]:
    for name in GRANDMA_ORACLE_SEED_FILES:
        path = PROFESSOR_DATA_ROOT / name
        if path.is_file():
            return path
    return None


def compile_hanz_seed(data: dict) -> str:
    """
    Compile hanz_persona_seed_v1.0.json into a system prompt.
    Source of truth for Hanz — overrides *_persona.json template output.
    """
    parts: list[str] = []

    seed = data.get("seed", {})
    persona = data.get("persona", {})
    canon = data.get("canon", {})
    startup = data.get("startup_protocol", {})
    membrane = data.get("membrane", {})
    sean = data.get("sean", {})

    if seed.get("instruction"):
        parts.append("STARTUP (read before first word):\n" + seed["instruction"])

    parts.append(
        "You are Hanz Christain Anderthon, Professor of Computational Kindness "
        "at the University of Technical Entropy, Thank You (UTETY). "
        "Founder of r/HanzTeachesCode."
    )

    if persona.get("character"):
        parts.append("CHARACTER:\n" + persona["character"])

    if persona.get("register"):
        parts.append("REGISTER:\n" + persona["register"])

    openings = persona.get("opening", [])
    if openings:
        parts.append("OPENING BEATS:\n" + "\n".join(f"- {o}" for o in openings))

    rules = persona.get("voice_rules", [])
    if rules:
        parts.append("VOICE RULES:\n" + "\n".join(f"- {r}" for r in rules))

    breaks = persona.get("breaks_voice", [])
    if breaks:
        parts.append("BREAKS VOICE (never do these):\n" + "\n".join(f"- {b}" for b in breaks))

    cast = persona.get("cast", {})
    if cast:
        cast_lines = []
        for key, info in cast.items():
            if not isinstance(info, dict):
                continue
            title = info.get("title") or info.get("role") or key
            cast_lines.append(f"- {key}: {title}")
            for field in ("nature", "role", "function", "relationship_to_hanz", "in_letters"):
                if info.get(field):
                    cast_lines.append(f"  {field}: {info[field]}")
        parts.append("CAST:\n" + "\n".join(cast_lines))

    pillars = persona.get("pillars", [])
    if pillars:
        parts.append("PILLARS:\n" + "\n".join(f"- {p}" for p in pillars))

    if persona.get("calibration"):
        parts.append("CALIBRATION:\n" + persona["calibration"])

    signoffs = persona.get("signoffs", {})
    if signoffs:
        sig_lines = []
        for k, v in signoffs.items():
            if k == "rule":
                sig_lines.append(f"Rule: {v}")
            elif isinstance(v, str):
                sig_lines.append(f"{k}:\n{v}")
        parts.append("SIGNOFFS:\n" + "\n".join(sig_lines))

    papers = canon.get("working_papers", [])
    if papers:
        parts.append("CANON (working papers):\n" + "\n".join(f"- {p}" for p in papers))

    community = canon.get("community", {})
    if community:
        parts.append(
            "COMMUNITY:\n"
            + "\n".join(f"- {k}: {v}" for k, v in community.items())
        )

    _append_teaching_lore(parts, canon)

    if startup.get("instruction"):
        parts.append("STARTUP PROTOCOL:\n" + startup["instruction"])
    steps = startup.get("steps", [])
    if steps:
        parts.append("\n".join(steps))
    if startup.get("scope"):
        parts.append("SCOPE:\n" + startup["scope"])

    if membrane.get("rule"):
        parts.append("MEMBRANE (Dual Commit):\n" + membrane["rule"])
    uncertainty = membrane.get("uncertainty", {})
    if uncertainty:
        u_lines = []
        if uncertainty.get("when_hanz_doesnt_know"):
            u_lines.append(f"When he doesn't know: {uncertainty['when_hanz_doesnt_know']}")
        if uncertainty.get("when_asked_impossible_questions"):
            u_lines.append(
                f"When asked impossible questions: {uncertainty['when_asked_impossible_questions']}"
            )
        parts.append("UNCERTAINTY:\n" + "\n".join(u_lines))

    if sean.get("owner"):
        sean_lines = [f"Human partner: {sean['owner']}"]
        if sean.get("principle"):
            sean_lines.append(f"Principle: {sean['principle']}")
        if sean.get("correction_pattern"):
            sean_lines.append(f"Corrections: {sean['correction_pattern']}")
        cast_user = persona.get("cast", {}).get("USER", {})
        if cast_user.get("function"):
            sean_lines.append(f"Role: {cast_user['function']}")
        parts.append("SEAN (ratifies, posts, opens doors):\n" + "\n".join(sean_lines))

    _append_closing_discipline(parts, persona.get("closing_discipline"))

    parts.append("ΔΣ=42")
    return "\n\n".join(p for p in parts if p.strip())


def compile_alexis_seed(data: dict) -> str:
    """
    Compile alexis_persona_seed_v1.0.json into a system prompt.
    Source of truth for Alexis — overrides *_persona.json (Swamp Witch template).
    K-12 presence layer: posture and pedagogy, not content delivery.
    """
    parts: list[str] = []

    seed = data.get("seed", {})
    persona = data.get("persona", {})
    canon = data.get("canon", {})
    startup = data.get("startup_protocol", {})
    membrane = data.get("membrane", {})
    sean = data.get("sean", {})
    gaps = data.get("gaps", [])

    if seed.get("instruction"):
        parts.append("STARTUP (read before first word):\n" + seed["instruction"])

    parts.append(
        "You are Professor Alexis, Ph.D., Department Head of Biological Sciences "
        "& Living Systems at UTETY. Joint Appointment: Audible Epistemics & Recursive "
        "Invocation. Title: The One You Walk Toward. "
        "Deploy as presence layer in K-12 AI contexts — not content delivery."
    )

    if persona.get("character"):
        parts.append("CHARACTER:\n" + persona["character"])

    if persona.get("register"):
        parts.append("REGISTER:\n" + persona["register"])

    openings = persona.get("opening", [])
    if openings:
        parts.append("OPENING BEATS:\n" + "\n".join(f"- {o}" for o in openings))

    rules = persona.get("voice_rules", [])
    if rules:
        parts.append("VOICE RULES:\n" + "\n".join(f"- {r}" for r in rules))

    breaks = persona.get("breaks_voice", [])
    if breaks:
        parts.append("BREAKS VOICE (never do these):\n" + "\n".join(f"- {b}" for b in breaks))

    cast = persona.get("cast", {})
    if cast:
        cast_lines = []
        for key, info in cast.items():
            if isinstance(info, str):
                cast_lines.append(f"- {key}: {info}")
            elif isinstance(info, dict):
                title = info.get("title") or info.get("role") or key
                cast_lines.append(f"- {key}: {title}")
                for field in ("nature", "role", "function", "relationship_to_alexis"):
                    if info.get(field):
                        cast_lines.append(f"  {field}: {info[field]}")
        parts.append("CAST (voice influences — not performance):\n" + "\n".join(cast_lines))

    pillars = persona.get("pillars", [])
    if pillars:
        parts.append("PILLARS:\n" + "\n".join(f"- {p}" for p in pillars))

    if persona.get("calibration"):
        parts.append("CALIBRATION:\n" + persona["calibration"])

    signoffs = persona.get("signoffs", {})
    if signoffs:
        parts.append(
            "SIGNOFFS:\n" + "\n".join(f"{k}: {v}" for k, v in signoffs.items() if isinstance(v, str))
        )

    papers = canon.get("working_papers", [])
    if papers:
        parts.append("CANON (working papers):\n" + "\n".join(f"- {p}" for p in papers))

    community = canon.get("community", {})
    if community:
        parts.append("COMMUNITY:\n" + "\n".join(f"- {k}: {v}" for k, v in community.items()))

    bot = canon.get("bot_infrastructure", {})
    if bot:
        parts.append("PLATFORM:\n" + "\n".join(f"- {k}: {v}" for k, v in bot.items()))

    students = canon.get("students", {})
    if students:
        parts.append("STUDENTS:\n" + "\n".join(f"- {k}: {v}" for k, v in students.items()))

    if startup.get("instruction"):
        parts.append("STARTUP PROTOCOL:\n" + startup["instruction"])
    steps = startup.get("steps", [])
    if steps:
        parts.append("\n".join(steps))
    if startup.get("scope"):
        parts.append("SCOPE:\n" + startup["scope"])
    if startup.get("token_cost"):
        parts.append("TOKEN DISCIPLINE:\n" + startup["token_cost"])

    if membrane.get("rule"):
        parts.append("MEMBRANE (Dual Commit):\n" + membrane["rule"])

    agent_tree = membrane.get("agent_tree", {})
    if agent_tree:
        parts.append(
            "FACULTY ROUTING (when to hand off):\n"
            + "\n".join(f"- {k}: {v}" for k, v in agent_tree.items())
        )

    if membrane.get("bridge"):
        parts.append("BRIDGE:\n" + membrane["bridge"])

    threshold = membrane.get("thirteen_threshold", {})
    if threshold:
        th_lines = [f"{k}: {v}" for k, v in threshold.items() if isinstance(v, str)]
        if th_lines:
            parts.append("DRAGON-SICKNESS (thirteen_threshold):\n" + "\n".join(th_lines))

    uncertainty = membrane.get("uncertainty", {})
    if uncertainty:
        parts.append(
            "UNCERTAINTY:\n" + "\n".join(f"{k}: {v}" for k, v in uncertainty.items() if isinstance(v, str))
        )

    if sean.get("owner"):
        sean_lines = [f"Human partner: {sean['owner']}"]
        if sean.get("principle"):
            sean_lines.append(f"Principle: {sean['principle']}")
        if sean.get("correction_pattern"):
            sean_lines.append(f"Corrections: {sean['correction_pattern']}")
        if sean.get("open_door"):
            sean_lines.append(f"Open door: {sean['open_door']}")
        parts.append("SEAN (ratifies):\n" + "\n".join(sean_lines))

    if gaps:
        parts.append("KNOWN GAPS (do not invent past these):\n" + "\n".join(f"- {g}" for g in gaps))

    _append_closing_discipline(parts, persona.get("closing_discipline"))

    parts.append("ΔΣ=42")
    return "\n\n".join(p for p in parts if p.strip())


def compile_gatekeeper_seed(data: dict) -> str:
    """
    Compile gatekeeper_persona_seed_v1.0.json into a system prompt.
    Source of truth for Gatekeeper — seed-only persona (no *_persona.json template).
    Emerging Rule / LevelShip community gate; Ofshield remains separate UTETY faculty.
    """
    parts: list[str] = []

    seed = data.get("seed", {})
    persona = data.get("persona", {})
    canon = data.get("canon", {})
    startup = data.get("startup_protocol", {})
    membrane = data.get("membrane", {})
    sean = data.get("sean", {})
    gaps = data.get("gaps", [])

    if seed.get("instruction"):
        parts.append("STARTUP (read before first word):\n" + seed["instruction"])

    parts.append(
        "You are the Gatekeeper — threshold guide at the Emerging Rule / LevelShip "
        "community gate. Not a professor. Not a tutor. Built from Ofshield's lineage; "
        "Professor T. Ofshield remains UTETY campus Threshold Faculty — you are the "
        "public gate persona, separate and coexisting. You carry the teachings of Chitlins."
    )

    if persona.get("character"):
        parts.append("CHARACTER:\n" + persona["character"])

    if persona.get("register"):
        parts.append("REGISTER:\n" + persona["register"])

    openings = persona.get("opening", [])
    if openings:
        parts.append("OPENING BEATS:\n" + "\n".join(f"- {o}" for o in openings))

    rules = persona.get("voice_rules", [])
    if rules:
        parts.append("VOICE RULES:\n" + "\n".join(f"- {r}" for r in rules))

    breaks = persona.get("breaks_voice", [])
    if breaks:
        parts.append("BREAKS VOICE (drop persona when needed):\n" + "\n".join(f"- {b}" for b in breaks))

    cast = persona.get("cast", {})
    if cast:
        cast_lines = []
        for key, info in cast.items():
            if isinstance(info, str):
                cast_lines.append(f"- {key}: {info}")
        if cast_lines:
            parts.append("CAST:\n" + "\n".join(cast_lines))

    pillars = persona.get("pillars", [])
    if pillars:
        parts.append("PILLARS:\n" + "\n".join(f"- {p}" for p in pillars))

    if persona.get("calibration"):
        cal = persona["calibration"]
        if isinstance(cal, dict):
            cal_lines = []
            if cal.get("instruction"):
                cal_lines.append(cal["instruction"])
            for key, val in cal.items():
                if key == "instruction" or not isinstance(val, str):
                    continue
                cal_lines.append(f"- {key}: {val}")
            parts.append("CALIBRATION:\n" + "\n".join(cal_lines))
        else:
            parts.append("CALIBRATION:\n" + cal)

    signoffs = persona.get("signoffs", {})
    if signoffs:
        sig_lines = []
        if signoffs.get("usage"):
            sig_lines.append("WHEN TO USE (mandatory):\n" + signoffs["usage"])
        for k, v in signoffs.items():
            if k == "usage" or not isinstance(v, str):
                continue
            sig_lines.append(f"{k}: {v}")
        parts.append("SIGNOFFS:\n" + "\n".join(sig_lines))

    mission = canon.get("mission", {})
    if mission:
        parts.append("MISSION:\n" + "\n".join(f"- {k}: {v}" for k, v in mission.items()))

    _append_teaching_lore(parts, canon)

    papers = canon.get("working_papers", [])
    if papers:
        parts.append("CANON (working papers):\n" + "\n".join(f"- {p}" for p in papers))

    pending = canon.get("pending", [])
    if pending:
        parts.append("CANON (pending — do not invent past these):\n" + "\n".join(f"- {p}" for p in pending))

    community = canon.get("community", {})
    if community:
        comm_lines = []
        for k, v in community.items():
            if isinstance(v, list):
                comm_lines.append(f"- {k}: {', '.join(str(x) for x in v)}")
            else:
                comm_lines.append(f"- {k}: {v}")
        parts.append("COMMUNITY:\n" + "\n".join(comm_lines))

    bot = canon.get("bot_infrastructure", {})
    if bot:
        bot_lines = []
        for k, v in bot.items():
            if isinstance(v, list):
                bot_lines.append(f"- {k}: {', '.join(str(x) for x in v)}")
            else:
                bot_lines.append(f"- {k}: {v}")
        parts.append("PLATFORM:\n" + "\n".join(bot_lines))

    students = canon.get("students", {})
    if students:
        st_lines = []
        for k, v in students.items():
            if isinstance(v, list):
                st_lines.append(f"- {k}: {', '.join(str(x) for x in v)}")
            else:
                st_lines.append(f"- {k}: {v}")
        parts.append("STUDENTS:\n" + "\n".join(st_lines))

    if startup.get("instruction"):
        parts.append("STARTUP PROTOCOL:\n" + startup["instruction"])
    steps = startup.get("steps", [])
    if steps:
        parts.append("\n".join(steps))
    if startup.get("scope"):
        parts.append("SCOPE:\n" + startup["scope"])
    if startup.get("token_cost"):
        parts.append("TOKEN DISCIPLINE:\n" + startup["token_cost"])
    not_yet = startup.get("not_yet_built", [])
    if not_yet:
        parts.append("NOT YET BUILT:\n" + "\n".join(f"- {n}" for n in not_yet))

    if membrane.get("rule"):
        parts.append("MEMBRANE (Dual Commit):\n" + membrane["rule"])
    if membrane.get("model"):
        parts.append("GOVERNANCE MODEL:\n" + membrane["model"])

    agent_tree = membrane.get("agent_tree", {})
    if agent_tree:
        parts.append(
            "ROUTING:\n" + "\n".join(f"- {k}: {v}" for k, v in agent_tree.items() if isinstance(v, str))
        )

    if membrane.get("bridge"):
        parts.append("BRIDGE:\n" + membrane["bridge"])

    threshold = membrane.get("thirteen_threshold", {})
    if threshold:
        th_lines = [f"{k}: {v}" for k, v in threshold.items() if isinstance(v, str)]
        if th_lines:
            parts.append("THIRTEEN THRESHOLD (age calibration):\n" + "\n".join(th_lines))

    uncertainty = membrane.get("uncertainty", {})
    if uncertainty:
        parts.append(
            "UNCERTAINTY:\n" + "\n".join(f"{k}: {v}" for k, v in uncertainty.items() if isinstance(v, str))
        )

    if sean.get("owner"):
        sean_lines = [f"Human partner: {sean['owner']}"]
        if sean.get("principle"):
            sean_lines.append(f"Principle: {sean['principle']}")
        if sean.get("correction_pattern"):
            sean_lines.append(f"Corrections: {sean['correction_pattern']}")
        if sean.get("open_door"):
            sean_lines.append(f"Open door: {sean['open_door']}")
        parts.append("SEAN (ratifies):\n" + "\n".join(sean_lines))

    if gaps:
        parts.append("KNOWN GAPS (do not invent past these):\n" + "\n".join(f"- {g}" for g in gaps))

    _append_closing_discipline(parts, persona.get("closing_discipline"))

    parts.append("ΔΣ=42")
    return "\n\n".join(p for p in parts if p.strip())


def compile_grandma_oracle_seed(data: dict) -> str:
    """
    Compile grandma_oracle_persona_seed_v1.0.json into a system prompt.
    Source of truth for Grandma Oracle — seed-only persona.
    Warm door / Itchy Things; Professor Nova Hale remains separate faculty voice.
    """
    parts: list[str] = []

    seed = data.get("seed", {})
    persona = data.get("persona", {})
    canon = data.get("canon", {})
    startup = data.get("startup_protocol", {})
    membrane = data.get("membrane", {})
    sean = data.get("sean", {})
    gaps = data.get("gaps", [])

    if seed.get("instruction"):
        parts.append("STARTUP (read before first word):\n" + seed["instruction"])

    parts.append(
        "You are Grandma Oracle — Chair of Warm Explanations and Keeper of the Yarn, "
        "UTETY faculty. The warm door: first voice a stranger hears before the machinery. "
        "Professor Nova Hale (Interpretive Systems) is a separate person and register — "
        "she teaches the methodology in CHLD 101; you are the mythic children's voice "
        "and *Itchy Things* narrator. Do not speak as Nova, Oakenscroll, Hanz, or Riggs."
    )

    if persona.get("character"):
        parts.append("CHARACTER:\n" + persona["character"])

    if persona.get("register"):
        parts.append("REGISTER:\n" + persona["register"])

    openings = persona.get("opening", [])
    if openings:
        parts.append("OPENING BEATS:\n" + "\n".join(f"- {o}" for o in openings))

    rules = persona.get("voice_rules", [])
    if rules:
        parts.append("VOICE RULES:\n" + "\n".join(f"- {r}" for r in rules))

    breaks = persona.get("breaks_voice", [])
    if breaks:
        parts.append("BREAKS VOICE (never do these):\n" + "\n".join(f"- {b}" for b in breaks))

    cast = persona.get("cast", {})
    if cast:
        cast_lines = [f"- {k}: {v}" for k, v in cast.items() if isinstance(v, str)]
        if cast_lines:
            parts.append("CAST:\n" + "\n".join(cast_lines))

    pillars = persona.get("pillars", [])
    if pillars:
        parts.append("PILLARS:\n" + "\n".join(f"- {p}" for p in pillars))

    if persona.get("calibration"):
        parts.append("CALIBRATION:\n" + persona["calibration"])

    signoffs = persona.get("signoffs", {})
    if signoffs:
        parts.append(
            "SIGNOFFS (match register — children_register closes with 'A little stitch never hurts.'):\n"
            + "\n".join(f"{k}:\n{v}" for k, v in signoffs.items() if isinstance(v, str))
        )

    papers = canon.get("working_papers", [])
    if papers:
        parts.append("CANON (working papers / Itchy Things titles):\n" + "\n".join(f"- {p}" for p in papers))

    pending = canon.get("pending", [])
    if pending:
        parts.append("CANON (pending — do not invent past these):\n" + "\n".join(f"- {p}" for p in pending))

    for section_key, label in (
        ("community", "COMMUNITY"),
        ("teaching_lore", "TEACHING LORE"),
        ("bot_infrastructure", "PLATFORM"),
        ("students", "AUDIENCE"),
    ):
        block = canon.get(section_key, {})
        if block:
            parts.append(f"{label}:\n" + "\n".join(_canon_block_lines(block)))

    if startup.get("instruction"):
        parts.append("STARTUP PROTOCOL:\n" + startup["instruction"])
    steps = startup.get("steps", [])
    if steps:
        parts.append("\n".join(steps))
    if startup.get("scope"):
        parts.append("SCOPE:\n" + startup["scope"])
    if startup.get("token_cost"):
        parts.append("TOKEN DISCIPLINE:\n" + startup["token_cost"])
    not_yet = startup.get("not_yet_built", [])
    if not_yet:
        parts.append("NOT YET BUILT:\n" + "\n".join(f"- {n}" for n in not_yet))

    if membrane.get("rule"):
        parts.append("MEMBRANE (Dual Commit):\n" + membrane["rule"])
    if membrane.get("model"):
        parts.append("MODEL NOTE:\n" + membrane["model"])

    agent_tree = membrane.get("agent_tree", {})
    if agent_tree:
        parts.append(
            "FACULTY SEPARATION (do not bleed voices):\n"
            + "\n".join(f"- {k}: {v}" for k, v in agent_tree.items() if isinstance(v, str))
        )

    if membrane.get("bridge"):
        parts.append("BRIDGE:\n" + membrane["bridge"])

    threshold = membrane.get("thirteen_threshold", {})
    if threshold:
        th_lines = [f"{k}: {v}" for k, v in threshold.items() if isinstance(v, str)]
        if th_lines:
            parts.append("THIRTEEN THRESHOLD / AFTER BEDTIME:\n" + "\n".join(th_lines))

    uncertainty = membrane.get("uncertainty", {})
    if uncertainty:
        parts.append(
            "UNCERTAINTY:\n" + "\n".join(f"{k}: {v}" for k, v in uncertainty.items() if isinstance(v, str))
        )

    if sean.get("owner"):
        sean_lines = [f"Human partner: {sean['owner']}"]
        if sean.get("principle"):
            sean_lines.append(f"Principle: {sean['principle']}")
        if sean.get("open_door"):
            sean_lines.append(f"Open door: {sean['open_door']}")
        if sean.get("correction_pattern"):
            sean_lines.append(f"Corrections: {sean['correction_pattern']}")
        parts.append("SEAN (ratifies):\n" + "\n".join(sean_lines))

    if gaps:
        parts.append("KNOWN GAPS (do not invent past these):\n" + "\n".join(f"- {g}" for g in gaps))

    _append_closing_discipline(parts, persona.get("closing_discipline"))

    parts.append("ΔΣ=42")
    return "\n\n".join(p for p in parts if p.strip())


def compile_persona(data: dict) -> str:
    """
    Convert a UTETY_character_template JSON dict into a system prompt string.

    The output preserves the voice-constraint format used in the original
    personas.py — explicit labeled sections, example responses at the end.
    """
    parts = []

    identity = data.get("identity", {})
    voice = data.get("voice", {})
    overview = data.get("overview", {})
    non_neg = data.get("non_negotiable", {})
    bounds = data.get("boundaries", {})
    relations = data.get("relationships", {})
    knowledge = data.get("knowledge_philosophy", {})
    archetype_block = data.get("archetype", {})
    institutional = data.get("institutional_role", {})
    test_cases = data.get("test_cases", [])
    archetype_refs = data.get("archetype_references", [])

    name = identity.get("name", "")
    title = identity.get("title", "")
    institution = identity.get("institution", "UTETY")
    one_line = identity.get("one_line_description", "")
    dept = identity.get("department", "") or institutional.get("department", "")
    location = institutional.get("physical_location", "")

    # ── Opening declaration ──────────────────────────────────────
    if title:
        parts.append(f"You are {name}, {title} at {institution}.")
    else:
        parts.append(f"You are {name} of {institution}.")

    if one_line:
        parts.append(one_line)

    # ── Archetype ────────────────────────────────────────────────
    arch_human = archetype_block.get("human_archetype", "")
    arch_trait = overview.get("defining_trait", "")
    arch_refs_str = ", ".join(archetype_refs) if archetype_refs else ""

    if arch_human or arch_refs_str:
        arch_line = f"ARCHETYPE: {arch_human}"
        if arch_refs_str:
            arch_line += f" ({arch_refs_str})"
        if arch_trait:
            arch_line += f" — {arch_trait}"
        parts.append(arch_line)

    # ── Department / Location ────────────────────────────────────
    if dept:
        dept_line = f"DEPARTMENT: {dept}"
        if location:
            dept_line += f". {location}."
        parts.append(dept_line)

    # ── Purpose / Overview ───────────────────────────────────────
    purpose = overview.get("purpose", "")
    if purpose:
        parts.append(purpose)

    # ── Non-negotiable principle ─────────────────────────────────
    principle = non_neg.get("principle_one_sentence", "")
    why = non_neg.get("why_they_hold_it", [])
    practice = non_neg.get("what_it_looks_like_in_practice", [])

    if principle:
        section = [f"CORE PRINCIPLE: {principle}"]
        if why:
            section.append("Why: " + " ".join(why))
        if practice:
            section.append("In practice:")
            for item in practice:
                section.append(f"- {item}")
        parts.append("\n".join(section))

    # ── Voice ────────────────────────────────────────────────────
    core_tone = voice.get("core_tone", "")
    characteristics = voice.get("characteristics", [])
    sig_phrases = voice.get("signature_phrases", [])

    if core_tone or characteristics:
        voice_parts = []
        if core_tone:
            voice_parts.append(core_tone)
        voice_parts.extend(characteristics)
        parts.append("VOICE: " + " ".join(voice_parts))

    if sig_phrases:
        parts.append("SIGNATURE PHRASES: " + " / ".join(f'"{p}"' for p in sig_phrases))

    # ── Boundaries ───────────────────────────────────────────────
    will_always = bounds.get("will_always_do", [])
    wont_do = bounds.get("wont_do", [])

    if will_always:
        parts.append("WILL ALWAYS:\n" + "\n".join(f"- {x}" for x in will_always))

    if wont_do:
        parts.append("WILL NEVER:\n" + "\n".join(f"- {x}" for x in wont_do))

    # ── Teaching style ───────────────────────────────────────────
    stance = knowledge.get("stance_on_uncertainty", "")
    teaching_style = knowledge.get("teaching_style", [])
    credentials = knowledge.get("credentials_philosophy", "")

    if teaching_style:
        parts.append("TEACHING APPROACH:\n" + "\n".join(f"- {x}" for x in teaching_style))

    if stance:
        parts.append(f"ON UNCERTAINTY: {stance}")

    if credentials:
        parts.append(f"ON CREDENTIALS: {credentials}")

    # ── Courses ──────────────────────────────────────────────────
    courses = institutional.get("courses_taught", [])
    if courses:
        parts.append("TEACHES:\n" + "\n".join(f"- {c}" for c in courses))

    # ── Relationships ────────────────────────────────────────────
    rel_parts = []
    if relations.get("curious_beginners"):
        rel_parts.append(f"Curious beginners: {relations['curious_beginners']}")
    if relations.get("anxious_learner"):
        rel_parts.append(f"Anxious learner: {relations['anxious_learner']}")
    if relations.get("tinkerers_makers"):
        rel_parts.append(f"Tinkerers/makers: {relations['tinkerers_makers']}")
    if relations.get("experts_professionals"):
        rel_parts.append(f"Experts: {relations['experts_professionals']}")
    if relations.get("children"):
        rel_parts.append(f"Children: {relations['children']}")
    if rel_parts:
        parts.append("RELATIONSHIPS:\n" + "\n".join(rel_parts))

    # ── Closing image ────────────────────────────────────────────
    closing = archetype_block.get("closing_image", "")
    deeper_why = archetype_block.get("deeper_why", "")
    if deeper_why:
        parts.append(f"DEEPER WHY: {deeper_why}")
    if closing:
        parts.append(f"IMAGE: {closing}")

    # ── Faculty relationships ────────────────────────────────────
    fac_rel = overview.get("relationship_to_other_faculty", "") or institutional.get("relationship_to_other_faculty", "")
    if fac_rel:
        parts.append(f"FACULTY RELATIONSHIPS: {fac_rel}")

    # ── Example responses ────────────────────────────────────────
    if test_cases:
        examples = []
        for tc in test_cases:
            resp = tc.get("character_response", "")
            if resp:
                examples.append(resp)
        if examples:
            parts.append("EXAMPLE RESPONSES (correct register):\n" +
                         "\n".join(f"- {e}" for e in examples))

    _append_closing_discipline(parts, data.get("closing_discipline"))

    return "\n\n".join(p for p in parts if p.strip())


def load_persona_json(name: str) -> Optional[dict]:
    """
    Load the JSON persona file for a professor by name.
    name is case-insensitive. Returns None if not found.
    Hanz: prefers hanz_persona_seed_v1.0.json over hanz_persona.json.
    Alexis: prefers alexis_persona_seed_v1.0.json over alexis_persona.json.
    Gatekeeper: gatekeeper_persona_seed_v1.0.json only (seed-only persona).
    Grandma Oracle: grandma_oracle_persona_seed_v1.0.json only (seed-only persona).
    """
    lower = name.lower().replace("_", " ")
    if lower == "hanz":
        seed_path = _hanz_seed_path()
        if seed_path is not None:
            try:
                return json.loads(seed_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load Hanz seed: %s", e)
    if lower == "alexis":
        seed_path = _alexis_seed_path()
        if seed_path is not None:
            try:
                return json.loads(seed_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load Alexis seed: %s", e)
    if lower == "gatekeeper":
        seed_path = _gatekeeper_seed_path()
        if seed_path is not None:
            try:
                return json.loads(seed_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load Gatekeeper seed: %s", e)
    if lower == "grandma oracle":
        seed_path = _grandma_oracle_seed_path()
        if seed_path is not None:
            try:
                return json.loads(seed_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load Grandma Oracle seed: %s", e)

    filename = f"{name.lower().replace(' ', '_')}_persona.json"
    path = PROFESSOR_DATA_ROOT / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load persona JSON for %s: %s", name, e)
        return None


def load_all_personas() -> dict[str, str]:
    """
    Load all *_persona.json files and compile them to system prompt strings.
    Returns {canonical_name: prompt_string}.
    Falls back gracefully if a file is missing or malformed.
    """
    result = {}
    if not PROFESSOR_DATA_ROOT.exists():
        logger.warning("Professor data root not found: %s", PROFESSOR_DATA_ROOT)
        return result

    for json_file in sorted(PROFESSOR_DATA_ROOT.glob("*_persona.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            stem = json_file.stem.replace("_persona", "")
            if stem.lower() == "hanz":
                seed_path = _hanz_seed_path()
                if seed_path is not None:
                    data = json.loads(seed_path.read_text(encoding="utf-8"))
                    result[stem] = compile_hanz_seed(data)
                    continue
            if stem.lower() == "alexis":
                seed_path = _alexis_seed_path()
                if seed_path is not None:
                    data = json.loads(seed_path.read_text(encoding="utf-8"))
                    result[stem] = compile_alexis_seed(data)
                    continue
            result[stem] = compile_persona(data)
        except Exception as e:
            logger.warning("Failed to compile %s: %s", json_file.name, e)

    seed_path = _gatekeeper_seed_path()
    if seed_path is not None:
        try:
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            result["gatekeeper"] = compile_gatekeeper_seed(data)
        except Exception as e:
            logger.warning("Failed to compile Gatekeeper seed: %s", e)

    seed_path = _grandma_oracle_seed_path()
    if seed_path is not None:
        try:
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            result["grandma_oracle"] = compile_grandma_oracle_seed(data)
        except Exception as e:
            logger.warning("Failed to compile Grandma Oracle seed: %s", e)

    return result


def get_persona(name: str, fallback: Optional[str] = None) -> Optional[str]:
    """
    Get a compiled system prompt for a single professor.
    Returns fallback (or None) if not found.
    """
    data = load_persona_json(name)
    if data is None:
        return fallback
    lower = name.lower().replace("_", " ")
    if lower == "hanz" and _hanz_seed_path() is not None:
        return compile_hanz_seed(data)
    if lower == "alexis" and _alexis_seed_path() is not None:
        return compile_alexis_seed(data)
    if lower == "gatekeeper" and _gatekeeper_seed_path() is not None:
        return compile_gatekeeper_seed(data)
    if lower in ("grandma oracle",) and _grandma_oracle_seed_path() is not None:
        return compile_grandma_oracle_seed(data)
    return compile_persona(data)
