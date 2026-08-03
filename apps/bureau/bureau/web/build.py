#!/usr/bin/env python3
"""Generate the browser data from graph.py and inline it with the engine.

The data — every office, document, rule and line of prose — is exported from
the Python rather than hand-copied into JS. That is deliberate: the previous
build kept two copies of the prose and the differential compared only state, so
a wording divergence would have passed green. There is now one source, so there
is nothing to diverge.

    python3 bureau/web/build.py    ->  bureau/web/{data.json, bureau.html}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bureau import graph as G  # noqa: E402
from bureau import napkin as N  # noqa: E402

HERE = Path(__file__).resolve().parent

GOO_LINE = (
    "You notice you are not surprised. You check this twice. The room is warm "
    "and very slightly luminous, and you are fairly sure it was not before."
)


def export() -> dict:
    return {
        "starting_surprise": N.STARTING_SURPRISE,
        "goal": G.GOAL,
        "goo_line": GOO_LINE,
        "declaration": {f.value: t for f, t in N.DECLARATION.items()},
        "office_order": G.OFFICE_ORDER,
        "docs": {
            d.id: {"kind": d.kind, "qual": sorted(d.qual), "label": d.label}
            for d in G.DOCS.values()
        },
        "offices": {
            o.id: {
                "id": o.id,
                "name": o.name,
                "staff": o.staff,
                "issues": o.issues,
                "consumes_ticket": o.consumes_ticket,
                "requires": [{"kind": r.kind, "needs": sorted(r.needs)} for r in o.requires],
                "rule": o.rule,
                "on_refuse": list(o.on_refuse),
                "on_issue": o.on_issue,
            }
            for o in G.OFFICES.values()
        },
    }


def build() -> Path:
    data = export()
    (HERE / "data.json").write_text(json.dumps(data, indent=1), encoding="utf-8")

    page = (HERE / "page.html").read_text(encoding="utf-8")
    engine = (HERE / "engine.js").read_text(encoding="utf-8")
    engine = re.sub(r"\nif \(typeof module.*?\n\}\n", "\n", engine, flags=re.S)

    blob = json.dumps(data, ensure_ascii=False)
    if "</script" in engine or "</script" in blob:
        sys.exit("payload contains a script-closing sequence; refusing to inline")

    marker = "/* ENGINE */"
    if marker not in page:
        sys.exit("page.html lost its /* ENGINE */ marker")

    out = page.replace(marker, "var BUREAU_DATA = " + blob + ";\n" + engine)
    dest = HERE / "bureau.html"
    dest.write_text(out, encoding="utf-8")
    return dest


if __name__ == "__main__":
    p = build()
    print(f"{p} ({p.stat().st_size:,} bytes)")
