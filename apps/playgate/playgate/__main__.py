"""playgate CLI: serve the UIs, or lint the catalog without serving anything."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import catalog as catalog_mod
from . import server as server_mod
from .disposition import Log
from .interruption import InterruptionError

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data"


def _load(catalog_path: Path):
    try:
        return catalog_mod.load(catalog_path)
    except (InterruptionError, OSError, json.JSONDecodeError) as exc:
        print(f"catalog: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="playgate")
    parser.add_argument("--catalog", type=Path, default=catalog_mod.DEFAULT_CATALOG)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the loopback host")
    serve.add_argument("--port", type=int, default=server_mod.DEFAULT_PORT)
    serve.add_argument("--log", type=Path, default=DEFAULT_DATA / "requests.jsonl")
    serve.add_argument("--subject", action="append", default=None,
                       help="a child who may ask; repeatable. Required.")

    lint = sub.add_parser("lint", help="load the catalog and report, without serving")
    lint.add_argument("--strict", action="store_true",
                      help="exit non-zero if any entry is unmeasured")

    args = parser.parse_args(argv)
    apps = _load(args.catalog)

    if args.command == "lint":
        return _lint(apps, strict=args.strict)

    if not args.subject:
        print("at least one --subject is required: the kid UI offers a roster, "
              "not a text box", file=sys.stderr)
        return 2

    log = Log(path=args.log, roster=tuple(args.subject))
    httpd = server_mod.serve(apps, log, port=args.port)
    print(f"playgate on http://{server_mod.DEFAULT_HOST}:{args.port}/kid/ "
          f"(parent inbox at /parent/)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def _lint(apps, *, strict: bool) -> int:
    unmeasured = []
    for app in apps:
        state = app.view()["interruption"]["provenance"]
        print(f"{app.id:24} {state}")
        if state != "measured":
            unmeasured.append(app.id)

    if not unmeasured:
        return 0
    print(f"\n{len(unmeasured)} of {len(apps)} entries are not measured: "
          f"{', '.join(unmeasured)}", file=sys.stderr)
    print("Measuring one means watching a child play it for ten minutes and "
          "counting. There is no other way to reach that state.", file=sys.stderr)
    return 1 if strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
