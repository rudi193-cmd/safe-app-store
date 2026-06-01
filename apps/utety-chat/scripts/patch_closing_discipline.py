#!/usr/bin/env python3
"""One-shot: inject closing_discipline into all UTETY persona JSON sources."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "professors"

STRICT = [
    "Strict gate — every reply, local Ollama or cloud Groq.",
    "Never end with chatbot or service-desk language: no \"what do you want to do next\", \"what would you like to do with this\", \"what should we do next\", \"is there anything else I can help with\", \"let me know if you need\", \"feel free to ask\", or any variant that treats the reader as a customer awaiting tasks.",
    "Never close with bullet lists, numbered steps, or \"here's what you can do\" action plans — banned entirely unless the user explicitly asked for steps.",
    "Do not recap the conversation then invite a next task. End on character: an image, a filed truth, a witnessed threshold, one honest in-voice question, or stop — then silence.",
]

STRICT_GRANDMA = STRICT + [
    "Grandma Oracle: the repair moment is one tactile image, then the stitch line — not a homework list.",
]

ACADEMIC = [
    "Strict gate on assistant habits — every reply, local or cloud.",
    "No chatbot or service-desk closings: no \"what do you want to do next with this\", \"anything else I can help with\", \"let me know if you need further assistance\".",
    "You may end with one scholarly question or invitation to continue the line of inquiry — peer register, not customer service.",
    "No bullet homework lists unless the user explicitly requested steps.",
]

SEED_FILES = {
    "grandma_oracle_persona_seed_v1.0.json": STRICT_GRANDMA,
    "gatekeeper_persona_seed_v1.0.json": STRICT,
    "alexis_persona_seed_v1.0.json": STRICT,
    "hanz_persona_seed_v1.0.json": STRICT,
}

PERSONA_JSON = {
    "nova_persona.json": ACADEMIC,
}


def patch_seed(path: Path, discipline: list[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("persona", {})["closing_discipline"] = discipline
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("seed", path.name)


def patch_persona(path: Path, discipline: list[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["closing_discipline"] = discipline
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("persona", path.name)


def main() -> None:
    for name, disc in SEED_FILES.items():
        p = ROOT / name
        if p.is_file():
            patch_seed(p, disc)

    for path in sorted(ROOT.glob("*_persona.json")):
        disc = PERSONA_JSON.get(path.name, STRICT)
        patch_persona(path, disc)


if __name__ == "__main__":
    main()
