"""playgate CLI: serve the UIs, or lint the catalog without serving anything."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import catalog as catalog_mod
from . import paths as paths_mod
from . import server as server_mod
from .disposition import Log
from .interruption import InterruptionError


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
    serve.add_argument("--log", type=Path, default=None,
                       help="disposition log; defaults under the vault (D8), "
                            "overridable with PLAYGATE_LOG")
    serve.add_argument("--apk-root", type=Path, default=None,
                       help="where the installable APKs live; defaults under "
                            "the vault, overridable with PLAYGATE_APK_DIR")
    serve.add_argument("--subject", action="append", default=None,
                       help="a child who may ask; repeatable. Required.")

    lint = sub.add_parser("lint", help="load the catalog and report, without serving")
    lint.add_argument("--strict", action="store_true",
                      help="exit non-zero if any entry is unmeasured")

    verify = sub.add_parser("verify", help="walk the disposition chain (needs nestor)")
    verify.add_argument("--log", type=Path, default=None,
                        help="disposition log; same default as serve")
    verify.add_argument("--expect-head", default=None,
                        help="a head recorded earlier, from somewhere this app "
                             "cannot reach. Without it the newest line is "
                             "unvouched — nothing follows it.")

    args = parser.parse_args(argv)

    # Before the catalog load: verifying the record of what was already decided
    # must not depend on the catalog still being loadable today.
    if args.command == "verify":
        return _verify(args.log or paths_mod.log_path(), args.expect_head)

    apps = _load(args.catalog)

    if args.command == "lint":
        return _lint(apps, strict=args.strict)

    if not args.subject:
        print("at least one --subject is required: the kid UI offers a roster, "
              "not a text box", file=sys.stderr)
        return 2

    log_path = args.log or paths_mod.log_path()
    apk_root = args.apk_root or paths_mod.apk_dir()

    staged = paths_mod.stage_seed_apks(apps, apk_root)
    if staged:
        print(f"  staged {len(staged)} seed apk(s): {', '.join(staged)}")

    log = Log(path=log_path, roster=tuple(args.subject))
    httpd = server_mod.serve(apps, log, port=args.port, apk_root=apk_root)
    print(f"playgate on http://{server_mod.DEFAULT_HOST}:{args.port}/kid/ "
          f"(parent inbox at /parent/)")
    # Printed rather than assumed: an operator should be able to see where the
    # record of their child's requests is actually going.
    print(f"  log:  {log_path}")
    print(f"  apks: {apk_root}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def _verify(log_path: Path, expect_head: "str | None") -> int:
    # Imported here, not at module scope: the verifier is an injected seam, and
    # `playgate serve` must still start on a host where Nestor is not installed.
    from . import audit

    result = audit.verify(log_path, expected_head=expect_head)
    print(f"log:  {log_path}")

    if result["status"] == audit.OK:
        print(f"✓ {result['detail']}")
        if not expect_head:
            # Not a footnote: without an anchor the walk is silent about the one
            # line most worth editing, and a bare ✓ reads as if it were not.
            print("  ! the newest line is unvouched — nothing follows it. "
                  "Record the head below somewhere this app cannot reach and "
                  "pass it back as --expect-head.")
        print(f"  head {_head_of(log_path)}")
        return 0

    print(f"✗ {result['detail']}", file=sys.stderr)
    if result["status"] == audit.UNVERIFIABLE:
        # A missing verifier is not a clean log and must not exit like one.
        return 3
    return 1


def _head_of(log_path: Path) -> str:
    from .disposition import Log

    return Log(path=log_path, roster=("_",)).head()


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
