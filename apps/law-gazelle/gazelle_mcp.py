#!/usr/bin/env python3
"""
gazelle_mcp.py — Law Gazelle MCP server (stdio JSON-RPC 2.0).

Tools exposed:
  gazelle_sync      — sync Nest → cases/ and return manifest
  gazelle_briefing  — full briefing packet (urgent + milestones + cross-case)
  gazelle_urgent    — urgent queue only
  gazelle_detail    — drill-down on a single item
  gazelle_note      — add a note to the sidecar
  gazelle_resolve   — mark an item resolved in the sidecar
  gazelle_schedule  — schedule response packet (May 30 letter)
  gazelle_draft     — document drafting context + template
  gazelle_save      — save LLM-produced document to Nest

b17: LGMCP1  ΔΣ=42

Usage (.mcp.json):
  {"command": "python3", "args": ["/path/to/law-gazelle/gazelle_mcp.py"]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

import case_store
import document_store
import gazelle_state

# ── Tool definitions ──────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "gazelle_sync",
        "description": (
            "Sync Nest databases into Law Gazelle's local cases/ directory. "
            "Call this at the start of a legal session to ensure fresh data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "gazelle_briefing",
        "description": (
            "Return the full Law Gazelle briefing packet: urgent queue, milestones, "
            "and cross-case intersections. Use this to orient at the start of a legal session."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_session": {
                    "type": "boolean",
                    "description": "Include session_meta provenance (default false).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_urgent",
        "description": "Return the urgent queue only (deadlines + flags + high-priority atoms).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "show_resolved": {
                    "type": "boolean",
                    "description": "Include resolved/snoozed items (default false).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_detail",
        "description": (
            "Drill down on a single case item. "
            "Returns full detail dict including linked evidence, issues, and sidecar notes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_db": {
                    "type": "string",
                    "description": "Database: coparent, bankruptcy, workers_comp, or session.",
                },
                "item_type": {
                    "type": "string",
                    "description": (
                        "Item type: atom, flag, deadline, intersection, creditor, "
                        "context_event, case, session_meta, session_decision, artifact."
                    ),
                },
                "item_id": {
                    "type": "string",
                    "description": "Item identifier (e.g. ATM-001, FLAG-001, deadline:schedule).",
                },
            },
            "required": ["source_db", "item_type", "item_id"],
        },
    },
    {
        "name": "gazelle_note",
        "description": "Add a note to a case item in the sidecar (does not modify Nest).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_db": {"type": "string"},
                "item_type": {"type": "string"},
                "item_id": {"type": "string"},
                "body": {"type": "string", "description": "Note text."},
            },
            "required": ["source_db", "item_type", "item_id", "body"],
        },
    },
    {
        "name": "gazelle_resolve",
        "description": (
            "Mark a case item as resolved in the sidecar. "
            "Requires user confirmation before calling — this hides the item from the urgent queue."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_db": {"type": "string"},
                "item_type": {"type": "string"},
                "item_id": {"type": "string"},
            },
            "required": ["source_db", "item_type", "item_id"],
        },
    },
    {
        "name": "gazelle_schedule",
        "description": (
            "Return the schedule response briefing packet for the May 30 letter deadline: "
            "open schedule-domain atoms (ATM-001 etc.), parenting plan citations, deadline, "
            "and proposal summary. Use before drafting schedule proposals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["json", "markdown"],
                    "description": "Return raw dict fields (json) or drafting markdown (markdown). Default markdown.",
                },
                "include_resolved": {
                    "type": "boolean",
                    "description": "Include sidecar-resolved schedule atoms (default false).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_draft",
        "description": (
            "Get full drafting context for the LLM to produce a legal document: "
            "case parties, deadline, relevant atoms, structure template, and writing instructions. "
            "After authoring, call gazelle_save with the final body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": ["schedule_response", "letter_all_other", "general"],
                    "description": "Document type to draft.",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "markdown"],
                    "description": "Return structured dict (json) or LLM-ready markdown briefing (markdown). Default markdown.",
                },
                "atom_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional explicit atom IDs; otherwise auto-selected by doc_type.",
                },
            },
            "required": ["doc_type"],
        },
    },
    {
        "name": "gazelle_save",
        "description": (
            "Save an LLM-authored document to ~/Desktop/Nest/drafts/ (canonical). "
            "Use after gazelle_draft — pass the final letter body as markdown or plain text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "e.g. Campbell_schedule_response_2026-05-30.md",
                },
                "body": {
                    "type": "string",
                    "description": "Full document content.",
                },
                "dest": {
                    "type": "string",
                    "enum": ["nest", "cases"],
                    "description": "nest = ~/Desktop/Nest/drafts (default). cases = local sync copy only.",
                },
            },
            "required": ["filename", "body"],
        },
    },
]

# ── Dispatch ───────────────────────────────────────────────────────────────────

def _dispatch(name: str, args: dict) -> Any:
    if name == "gazelle_sync":
        return case_store.sync_cases()

    if name == "gazelle_briefing":
        return case_store.briefing_packet(
            include_session=args.get("include_session", False)
        )

    if name == "gazelle_urgent":
        return case_store.urgent_queue(
            show_resolved=args.get("show_resolved", False)
        )

    if name == "gazelle_detail":
        detail = case_store.get_item_detail(
            args["source_db"], args["item_type"], args["item_id"]
        )
        if detail is None:
            return {"error": f"Item not found: {args['item_type']} {args['item_id']}"}
        return detail

    if name == "gazelle_note":
        gazelle_state.add_note(
            args["source_db"], args["item_type"], args["item_id"], args["body"]
        )
        return {"ok": True, "message": "Note added."}

    if name == "gazelle_resolve":
        gazelle_state.mark_resolved(
            args["source_db"], args["item_type"], args["item_id"]
        )
        return {"ok": True, "message": "Marked resolved in sidecar."}

    if name == "gazelle_schedule":
        packet = case_store.schedule_response_packet(
            include_resolved=args.get("include_resolved", False)
        )
        if args.get("format", "markdown") == "json":
            return packet
        return {
            "markdown": case_store.format_schedule_response_text(packet),
            "atom_count": packet.get("atom_count"),
            "deadline": packet.get("deadline"),
        }

    if name == "gazelle_draft":
        ctx = document_store.draft_context(
            args["doc_type"],
            atom_ids=args.get("atom_ids"),
        )
        if ctx.get("error"):
            return ctx
        if args.get("format", "markdown") == "json":
            return ctx
        return {
            "markdown": document_store.format_draft_context_markdown(ctx),
            "doc_type": args["doc_type"],
            "atom_ids": ctx.get("atom_ids"),
        }

    if name == "gazelle_save":
        return document_store.save_document(
            args["filename"],
            args["body"],
            dest=args.get("dest", "nest"),
        )

    return {"error": f"Unknown tool: {name}"}


# ── JSON-RPC stdio loop ────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    line = json.dumps(obj, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _handle(req: dict) -> dict | None:
    rid = req.get("id")
    method = req.get("method", "")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "law-gazelle", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": _TOOLS}}

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        try:
            result = _dispatch(tool_name, tool_args)
            content = json.dumps(result, default=str, indent=2)
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": content}]},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            }

    if method == "notifications/initialized":
        return None  # no response for notifications

    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle(req)
        if resp is not None:
            _send(resp)


if __name__ == "__main__":
    main()
