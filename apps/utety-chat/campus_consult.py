#!/usr/bin/env python3
"""JSON sidecar for Ratatui Consultation Chamber → Ollama via consult_engine."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from consult_engine import consult


def main() -> int:
    try:
        req = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid json: {exc}"}))
        return 1

    professor = (req.get("professor") or "Willow").strip()
    message = (req.get("message") or "").strip()
    if not message:
        print(json.dumps({"ok": False, "error": "empty message"}))
        return 1

    course_code = req.get("course_code")
    history = req.get("history") or []
    compact = bool(req.get("compact", True))
    result = consult(
        professor=professor,
        message=message,
        history=history,
        course_code=course_code,
        compact=compact,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
