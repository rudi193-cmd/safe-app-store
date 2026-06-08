#!/usr/bin/env python3
"""
export_schedule_response.py — Export schedule response briefing for letter drafting.

Writes markdown (default) or JSON to stdout or a file. Syncs from Nest first unless
--no-sync is passed.

Usage:
    export_schedule_response.py
    export_schedule_response.py -o ~/Desktop/schedule_response_briefing.md
    export_schedule_response.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import case_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Export schedule response briefing")
    parser.add_argument(
        "-o", "--output", type=Path, help="Write to file instead of stdout"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON packet")
    parser.add_argument(
        "--no-sync", action="store_true", help="Skip Nest sync before export"
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Include sidecar-resolved schedule atoms",
    )
    args = parser.parse_args()

    if not args.no_sync:
        case_store.sync_cases()

    packet = case_store.schedule_response_packet(
        include_resolved=args.include_resolved
    )

    if args.json:
        text = json.dumps(packet, indent=2, default=str)
    else:
        text = case_store.format_schedule_response_text(packet)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output} ({len(text)} chars)", file=sys.stderr)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
