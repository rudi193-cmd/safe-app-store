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
  gazelle_schedule  — schedule response packet
  gazelle_draft     — document drafting context + template
  gazelle_save      — save LLM-produced document to Nest
  gazelle_commit    — write legal_commit manifest to Nest (session-end signal)

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
import commit_package
import document_store
import gazelle_state
import intelligence
import llm_client
import workflow

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
            "Return the schedule response briefing packet for the case response deadline: "
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
            "case parties, deadline, chronology (context events + meta dates), "
            "relevant atoms, structure template with [FACT NEEDED]/[VERIFY] flags, "
            "and writing instructions. After authoring, call gazelle_save with the final body. "
            "For chronology-only orientation, use gazelle_chronology."
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
        "name": "gazelle_chronology",
        "description": (
            "Build a dated event timeline from case data: context events, letter sent, "
            "response deadlines. Events are significance-tagged (🔴 critical, 🟡 notable) "
            "with [VERIFY] / [UNCERTAIN] flags and explicit gap reporting. "
            "Use before drafting to orient on facts and spot missing dates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "case": {
                    "type": "string",
                    "enum": ["coparent", "workers_comp"],
                    "description": "Case database to build chronology from (default: coparent).",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "markdown"],
                    "description": "Return raw dict (json) or rendered markdown table (markdown). Default markdown.",
                },
            },
            "required": [],
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
                    "description": "e.g. CaseDraft_schedule_response_2099-01-01.md",
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
    {
        "name": "gazelle_ai_brief",
        "description": (
            "Generate a local-Ollama briefing for a work item: summary, gaps, risks, next steps. "
            "Pass card_id from Today (e.g. coparent:atom:ATM-001) or full action_card dict."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "card_id": {
                    "type": "string",
                    "description": "Action card ID from Today screen.",
                },
                "card": {
                    "type": "object",
                    "description": "Optional full action_card dict (overrides card_id lookup).",
                },
                "include_courtlistener": {
                    "type": "boolean",
                    "description": "Verify citations with CourtListener if citations are present (default false).",
                },
                "force": {
                    "type": "boolean",
                    "description": "Bypass sidecar ai_cache and call Ollama again (default false).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_ai_draft",
        "description": (
            "Generate a local-Ollama first-pass draft letter from drafting context. "
            "Review before sending. Does not auto-save — use gazelle_save after review."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "card": {"type": "object"},
                "include_courtlistener": {"type": "boolean"},
                "force": {
                    "type": "boolean",
                    "description": "Bypass sidecar ai_cache and call Ollama again (default false).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_ai_rank_today",
        "description": (
            "Rank Today action cards by priority using local Ollama and Gazelle context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "show_resolved": {
                    "type": "boolean",
                    "description": "Include resolved items when building Today list (default false).",
                },
                "force": {
                    "type": "boolean",
                    "description": "Bypass sidecar ai_cache and call Ollama again (default false).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_ai_inspect_fact",
        "description": (
            "Inspect one Review Facts row with local Ollama and suggest verified / needs_source / "
            "do_not_use. Review-only; does not write sidecar verification status. "
            "Returns cached sidecar result when inputs unchanged."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fact_row": {
                    "type": "object",
                    "description": "A row from workflow.fact_review_rows.",
                },
                "card_id": {
                    "type": "string",
                    "description": "Optional Today card ID; first fact row for the card is inspected.",
                },
                "atom_id": {
                    "type": "string",
                    "description": "Optional atom ID within the card's Review Facts rows.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Bypass sidecar ai_cache and call Ollama again (default false).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gazelle_llm_health",
        "description": "Check local Ollama availability and list installed models.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gazelle_commit",
        "description": (
            "Write a legal_commit_<date>.json manifest to Nest at session end. "
            "Lists present case DBs and letter artifacts so nest_watcher can alert the fleet. "
            "Call after saving work to Nest (DBs, export JSON, drafts). Use dry_run to preview."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-line session summary (e.g. 'Schedule atoms updated; draft saved').",
                },
                "session_date": {
                    "type": "string",
                    "description": "Session date for filename, e.g. 2099-06-01 (default: today UTC).",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Build manifest without writing (default false).",
                },
            },
            "required": [],
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

    if name == "gazelle_chronology":
        chrono = document_store.chronology_builder(
            case=args.get("case", "coparent")
        )
        if args.get("format", "markdown") == "json":
            return chrono
        return {
            "markdown": document_store.format_chronology_markdown(chrono),
            "event_count": chrono.get("event_count"),
            "gaps": chrono.get("gaps"),
        }

    if name == "gazelle_save":
        return document_store.save_document(
            args["filename"],
            args["body"],
            dest=args.get("dest", "nest"),
        )

    if name == "gazelle_commit":
        return commit_package.write_commit_manifest(
            summary=args.get("summary", ""),
            session_date=args.get("session_date", ""),
            dry_run=args.get("dry_run", False),
        )

    if name == "gazelle_llm_health":
        cfg = llm_client.llm_config()
        health = llm_client.health_check()
        return {"config": cfg, **health}

    if name in (
        "gazelle_ai_brief",
        "gazelle_ai_draft",
        "gazelle_ai_rank_today",
        "gazelle_ai_inspect_fact",
    ):
        card = args.get("card")
        if not card and args.get("card_id"):
            cid = args["card_id"]
            cards = workflow.today_cards(show_resolved=True)
            card = next((c for c in cards if c.get("card_id") == cid), None)
            if not card:
                return {"ok": False, "error": f"card_id not found: {cid}"}
        include_cl = args.get("include_courtlistener", False)
        force = bool(args.get("force", False))
        if name == "gazelle_ai_rank_today":
            cards = workflow.today_cards(show_resolved=args.get("show_resolved", False))
            return intelligence.rank_today(
                cards, include_courtlistener=False, force=force
            )
        if name == "gazelle_ai_inspect_fact":
            row = args.get("fact_row")
            if not row:
                if not card:
                    return {"ok": False, "error": "Provide fact_row or card_id"}
                rows = workflow.fact_review_rows(card)
                atom_id = args.get("atom_id")
                row = next((r for r in rows if r.get("atom_id") == atom_id), None) if atom_id else (rows[0] if rows else None)
            if not row:
                return {"ok": False, "error": "No matching fact row found"}
            return intelligence.inspect_fact_row(row, force=force)
        if not card:
            return {"ok": False, "error": "Provide card_id or card"}
        if name == "gazelle_ai_brief":
            return intelligence.brief_card(
                card, include_courtlistener=include_cl, force=force
            )
        return intelligence.draft_from_card(
            card, include_courtlistener=include_cl, force=force
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
