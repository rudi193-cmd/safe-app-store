#!/usr/bin/env python3
"""
promote.py — CLI for story-timeline protocol operations.

Promote commonplace material (notes, books, ideas) into named timeline
entries with provenance and SOIL mirrors.

Usage:
  python3 promote.py create-project --title "My Novel"
  python3 promote.py create-timeline --project <id> --name "World chronology"
  python3 promote.py list-projects
  python3 promote.py list-timelines --project <id>
  python3 promote.py list-entries --timeline <id>
  python3 promote.py promote <source_id> --timeline <id> [--title "..."]
  python3 promote.py promote <source_id> --project <id> --timeline-name "Draft beats"
  python3 promote.py export-story --timeline <id> [--to story.md]
  python3 promote.py import-canon canon.md --timeline <id>
"""
from __future__ import annotations

import argparse
import json
import sys

import si_bridge as safe_integration
import story_protocol as proto


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_create_project(args: argparse.Namespace) -> int:
    project = proto.create_writing_project(
        args.title,
        summary=args.summary or "",
        status=args.status or "planning",
    )
    uuid = safe_integration.get_user_uuid()
    if uuid:
        import soil_protocol
        soil_protocol.mirror_protocol_record(project, uuid=uuid)
    _print_json(project)
    return 0


def cmd_create_timeline(args: argparse.Namespace) -> int:
    timeline = proto.create_timeline(
        args.project,
        args.name,
        timeline_kind=args.kind or "world",
        description=args.description or "",
    )
    uuid = safe_integration.get_user_uuid()
    if uuid:
        import soil_protocol
        soil_protocol.mirror_protocol_record(timeline, uuid=uuid)
        proto.wire_timeline_to_project(timeline["id"], args.project, uuid=uuid)
    _print_json(timeline)
    return 0


def cmd_list_projects(_args: argparse.Namespace) -> int:
    _print_json(proto.list_writing_projects())
    return 0


def cmd_list_timelines(args: argparse.Namespace) -> int:
    _print_json(proto.list_timelines(project_id=args.project))
    return 0


def cmd_list_entries(args: argparse.Namespace) -> int:
    _print_json(proto.list_timeline_entries(args.timeline))
    return 0


def cmd_export_story(args: argparse.Namespace) -> int:
    from pathlib import Path

    import export_story

    try:
        text = export_story.story_markdown(args.timeline)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not args.to:
        print(text, end="")
        return 0
    to = Path(args.to)
    if to.exists():
        print(f"error: {to} is there; a story is never written over", file=sys.stderr)
        return 2
    to.write_text(text, encoding="utf-8")
    print(f"wrote {to}")
    return 0


def cmd_import_canon(args: argparse.Namespace) -> int:
    import import_canon
    from pathlib import Path

    try:
        text = Path(args.file).read_text(encoding="utf-8")
        got = import_canon.import_canon(
            text, args.timeline, uuid=safe_integration.get_user_uuid(), mirror=not args.no_mirror
        )
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for f in got["added"]:
        print(f"added  {f['fact']}  (sealed at row {f['row']}, {f['from']})")
    for f in got["skipped"]:
        print(f"there  {f['fact']}")
    print(f"{len(got['added'])} added, {len(got['skipped'])} already on the timeline")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    timeline_id = args.timeline
    if not timeline_id and args.timeline_name:
        if not args.project:
            print("error: --project required when using --timeline-name", file=sys.stderr)
            return 2
        timeline = proto.find_timeline_by_name(args.project, args.timeline_name)
        if not timeline:
            print(
                f"error: timeline {args.timeline_name!r} not found under project {args.project}",
                file=sys.stderr,
            )
            return 1
        timeline_id = timeline["id"]
    if not timeline_id:
        print("error: provide --timeline or --timeline-name", file=sys.stderr)
        return 2

    uuid = safe_integration.get_user_uuid()
    result = proto.promote_to_timeline(
        args.source_id,
        timeline_id,
        title=args.title,
        summary=args.summary,
        order_index=args.order,
        world_date=args.world_date,
        entry_kind=args.entry_kind or "scene",
        uuid=uuid,
        mirror=not args.no_mirror,
    )
    _print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Story-timeline protocol: promote commonplace material into timelines"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_project = sub.add_parser("create-project", help="Create a writing project")
    p_project.add_argument("--title", required=True)
    p_project.add_argument("--summary", default="")
    p_project.add_argument("--status", default="planning")
    p_project.set_defaults(func=cmd_create_project)

    p_timeline = sub.add_parser("create-timeline", help="Create a named timeline")
    p_timeline.add_argument("--project", required=True, help="Writing project node id")
    p_timeline.add_argument("--name", required=True)
    p_timeline.add_argument("--kind", default="world", help="world | draft | process")
    p_timeline.add_argument("--description", default="")
    p_timeline.set_defaults(func=cmd_create_timeline)

    p_list_proj = sub.add_parser("list-projects", help="List writing projects")
    p_list_proj.set_defaults(func=cmd_list_projects)

    p_list_tl = sub.add_parser("list-timelines", help="List timelines")
    p_list_tl.add_argument("--project", help="Filter by project id")
    p_list_tl.set_defaults(func=cmd_list_timelines)

    p_list_ent = sub.add_parser("list-entries", help="List entries on a timeline")
    p_list_ent.add_argument("--timeline", required=True)
    p_list_ent.set_defaults(func=cmd_list_entries)

    p_promote = sub.add_parser("promote", help="Promote a source record to a timeline entry")
    p_promote.add_argument("source_id", help="Node id of note/book/commonplace source")
    p_promote.add_argument("--timeline", help="Timeline node id")
    p_promote.add_argument("--timeline-name", help="Timeline name (requires --project)")
    p_promote.add_argument("--project", help="Project id (for --timeline-name lookup)")
    p_promote.add_argument("--title", help="Override entry title")
    p_promote.add_argument("--summary", help="Override entry summary")
    p_promote.add_argument("--order", type=int, help="Order index on timeline")
    p_promote.add_argument("--world-date", dest="world_date", help="In-world date label")
    p_promote.add_argument("--entry-kind", default="scene", help="scene | beat | milestone | fact")
    p_promote.add_argument("--no-mirror", action="store_true", help="Skip SOIL mirrors")
    p_promote.set_defaults(func=cmd_promote)

    p_import = sub.add_parser("import-canon", help="Put what a game table sealed on a timeline, as fact entries")
    p_import.add_argument("file", help="A game box's canon, as session.py export-canon writes it")
    p_import.add_argument("--timeline", required=True, help="Timeline node id")
    p_import.add_argument("--no-mirror", action="store_true", help="Skip SOIL mirrors")
    p_import.set_defaults(func=cmd_import_canon)

    p_export = sub.add_parser("export-story", help="Export a timeline as story markdown for the game box")
    p_export.add_argument("--timeline", required=True, help="Timeline node id")
    p_export.add_argument("--to", help="Write to this file (never over one that is there)")
    p_export.set_defaults(func=cmd_export_story)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
