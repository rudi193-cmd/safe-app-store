"""The Intake Desk — CLI.

Enough surface to drive one real session by hand, with no model anywhere.
That is deliberate: the discipline is the product, and if it does not work
with a human doing all the checking, no amount of assistance saves it.

    python app.py interviewers
    python app.py consent grant-keeping --narrator slappy --by operator
    python app.py file --narrator slappy --taker penny --body-file interview.txt
    python app.py claim --statement <id> --span 0:41 --assertion "..."
    python app.py route --all
    python app.py docket --claim <id> --relation contradicts --source-kind vault
    python app.py rule --claim <id> --by wrench --confidence high
    python app.py queue
    python app.py export --format markdown --out testimony.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import consent as consent_mod  # noqa: E402
import desk  # noqa: E402
import desk_db  # noqa: E402
import export  # noqa: E402
import interviewer  # noqa: E402
import router  # noqa: E402
from subject_consent import ChainTamperError  # noqa: E402


def _stores(args):
    db = Path(args.db) if args.db else desk_db.default_db()
    return db, consent_mod.consent_store(db)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="intake-desk", description=__doc__)
    p.add_argument("--db", help="vault path (default: vault-rooted; INTAKE_DESK_DB overrides)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("interviewers", help="list injected interviewer profiles")

    b = sub.add_parser("brief", help="print an interviewer's brief")
    b.add_argument("--name", default="riggs")

    c = sub.add_parser("consent", help="grant or revoke (operator only — never the app)")
    c.add_argument("action", choices=["grant-keeping", "grant-publication", "revoke"])
    c.add_argument("--narrator", required=True)
    c.add_argument("--by", required=True)

    f = sub.add_parser("file", help="file a verbatim statement")
    f.add_argument("--narrator", required=True)
    f.add_argument("--taker", required=True)
    f.add_argument("--session", default="s1")
    f.add_argument("--body-file", required=True)
    f.add_argument("--medium", default="transcript")

    cl = sub.add_parser("claim", help="break a claim out of a statement")
    cl.add_argument("--statement", required=True)
    cl.add_argument("--span", required=True, help="START:END, character offsets")
    cl.add_argument("--assertion", required=True)
    cl.add_argument("--source-type", default="oral_history_consented")
    cl.add_argument("--occurred-at", help='when, as the narrator dated it — fuzzy is fine ("summer 1998")')
    cl.add_argument("--place")

    d = sub.add_parser("docket", help="record evidence — never a verdict")
    d.add_argument("--claim", required=True)
    d.add_argument("--relation", required=True,
                   choices=["corroborates", "contradicts", "contextualizes", "no_source_found"])
    d.add_argument("--source-kind", required=True,
                   choices=["vault", "public_record", "web", "operator"])
    d.add_argument("--source-ref")
    d.add_argument("--excerpt")
    d.add_argument("--by", default="operator")

    rt = sub.add_parser("route", help="run the routing pass — evidence, never a verdict")
    rt.add_argument("--claim")
    rt.add_argument("--all", action="store_true", help="sweep every unrouted claim")

    r = sub.add_parser("rule", help="a human judges a claim (not the narrator, not the taker)")
    r.add_argument("--claim", required=True)
    r.add_argument("--by", required=True)
    r.add_argument("--confidence", default="medium",
                   choices=["high", "medium", "low", "conflicting"])
    r.add_argument("--note", default="")
    r.add_argument("--uncheckable", action="store_true",
                   help="no source class could exist — a successful terminal outcome")

    pub = sub.add_parser("publish", help="mark a ruled claim as permitted to leave")
    pub.add_argument("--claim", required=True)

    w = sub.add_parser("withhold", help="stop the export, keep the record")
    w.add_argument("--claim")
    w.add_argument("--narrator")
    w.add_argument("--reason", default="")

    sub.add_parser("queue", help="the desk queue")

    an = sub.add_parser("anchor", help="print the chain heads to pin OUTSIDE this box")
    an.add_argument("--expect", help="path to a previously saved anchor file; verify against it")
    an.add_argument("--save", help="write the current heads to this path")

    e = sub.add_parser("export", help="egress — fails closed")
    e.add_argument("--format", choices=["json", "markdown"], default="json")
    e.add_argument("--out", required=True)

    args = p.parse_args(argv)
    db, store = _stores(args)

    if args.cmd == "interviewers":
        for name in interviewer.available():
            print(name)
        return 0
    if args.cmd == "brief":
        print(interviewer.load(args.name).brief())
        return 0
    if args.cmd == "consent":
        if args.action == "grant-keeping":
            consent_mod.grant_keeping(store, args.narrator, args.by)
        elif args.action == "grant-publication":
            consent_mod.grant_publication(store, args.narrator, args.by)
        else:
            consent_mod.revoke_all(store, args.narrator, args.by)
        print(f"{args.action}: {args.narrator}")
        return 0

    conn = desk_db.connect(db)
    try:
        if args.cmd == "file":
            sid = desk.file_statement(
                conn, consent_store=store, session_id=args.session,
                narrator_id=args.narrator, taker_id=args.taker,
                body=Path(args.body_file).read_text(encoding="utf-8"),
                medium=args.medium,
            )
            print(sid)
        elif args.cmd == "claim":
            start, _, end = args.span.partition(":")
            print(desk.add_claim(
                conn, consent_store=store,
                statement_id=args.statement, span=(int(start), int(end)),
                assertion=args.assertion, source_type=args.source_type,
                occurred_at=args.occurred_at, place=args.place))
        elif args.cmd == "docket":
            print(desk.add_docket_entry(
                conn, claim_id=args.claim, relation=args.relation,
                source_kind=args.source_kind, source_ref=args.source_ref,
                excerpt=args.excerpt, found_by=args.by))
        elif args.cmd == "route":
            if args.all:
                findings = router.route_all(conn)
            elif args.claim:
                findings = [router.route(conn, args.claim)]
            else:
                print("--claim or --all required", file=sys.stderr)
                return 2
            for f in findings:
                print(f"{f.claim_id}  {f.sentence()}")
            if not findings:
                print("nothing to route")
        elif args.cmd == "rule":
            if args.uncheckable:
                desk.mark_uncheckable(conn, claim_id=args.claim, ruled_by=args.by, note=args.note)
            else:
                desk.rule(conn, claim_id=args.claim, ruled_by=args.by,
                          confidence=args.confidence, note=args.note)
            print("ruled")
        elif args.cmd == "publish":
            desk.publish(conn, claim_id=args.claim)
            print("published")
        elif args.cmd == "withhold":
            if args.narrator:
                print(f"withheld {desk.withhold_narrator(conn, narrator_id=args.narrator, reason=args.reason)} claim(s)")
            elif args.claim:
                desk.withhold(conn, claim_id=args.claim, reason=args.reason)
                print("withheld")
            else:
                print("--claim or --narrator required", file=sys.stderr)
                return 2
        elif args.cmd == "queue":
            for state, n in desk.queue(conn).items():
                print(f"{state.upper():<16} {n}")
        elif args.cmd == "anchor":
            narrators = [r["narrator_id"] for r in conn.execute(
                "SELECT DISTINCT narrator_id FROM statements")]
            if args.expect:
                expected = json.loads(Path(args.expect).read_text())
                res = desk_db.verify_chains(store, narrators, expected)
                for n in res["tampered"]:
                    print(f"TAMPERED   {n}  (broken or truncated chain)")
                for n, d in res["moved"].items():
                    print(f"MOVED      {n}  anchored {d['expected'][:16]}… now {str(d['found'])[:16]}…")
                if res["valid"]:
                    print(f"intact — {len(res['heads'])} chain(s) match the anchor you held")
                else:
                    return 1
            else:
                heads = desk_db.chain_heads(store, narrators)
                for n, h in heads.items():
                    print(f"{h}  {n}")
                if args.save:
                    Path(args.save).write_text(json.dumps(heads, indent=2) + "\n")
                    print(f"\nsaved to {args.save} — keep it somewhere this machine cannot reach.")
                elif heads:
                    print("\nHold these outside the box. A chain whose writer can also rewrite")
                    print("its anchor vouches for nothing against that writer.")
        elif args.cmd == "export":
            fn = export.to_json if args.format == "json" else export.to_markdown
            print(fn(conn, consent_store=store, path=args.out))
    except (desk.DeskError, export.ExportRefused, interviewer.InterviewerError,
            router.RouterError, desk_db.VaultTampered, ChainTamperError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
