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
"""
from __future__ import annotations

import argparse
import json
import sys

import safe_integration
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
