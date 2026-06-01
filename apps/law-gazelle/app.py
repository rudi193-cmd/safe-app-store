"""
Law Gazelle — case command center. b17: E472A

Syncs Nest case databases and surfaces urgent flags, deadlines, and open atoms.

Usage:
  python3 app.py
  python3 app.py --sync-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gazelle_state
from case_store import (
    bankruptcy_overview,
    coparent_atoms,
    coparent_issues,
    cross_case_overview,
    format_detail_text,
    get_item_detail,
    list_artifacts,
    list_cases,
    milestone_banner,
    session_overview,
    sync_cases,
    urgent_queue,
    workers_comp_atoms,
    workers_comp_overview,
)

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane
    from screens.detail import DetailScreen, NoteModal, SnoozeModal
except ImportError:
    App = None
    DetailScreen = NoteModal = SnoozeModal = None  # type: ignore


def _sync_and_report(source: Path | None = None) -> dict:
    return sync_cases(source or Path.home() / "Desktop" / "Nest")


LawGazelleApp = None

if App is not None:

    class LawGazelleApp(App):
        """Law Gazelle case dashboard."""

        TITLE = "Law Gazelle"
        SUB_TITLE = "Case Command Center"

        CSS = """
        #milestones {
            height: auto;
            padding: 0 1;
            color: $warning;
            background: $surface;
        }
        #sync-status {
            height: auto;
            padding: 0 1;
            color: $text-muted;
        }
        .panel-table {
            height: 1fr;
        }
        """

        BINDINGS = [
            Binding("r", "refresh", "Refresh", show=True),
            Binding("v", "open_detail", "Detail", show=True),
            Binding("d", "mark_done", "Done", show=True),
            Binding("n", "add_note", "Note", show=True),
            Binding("s", "snooze", "Snooze", show=True),
            Binding("u", "toggle_resolved", "Resolved", show=True),
            Binding("o", "open_artifact", "Open", show=True),
            Binding("q", "quit", "Quit", show=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.show_resolved = False
            self._item_by_key: dict[str, dict] = {}

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static("", id="milestones")
            yield Static("", id="sync-status")
            with TabbedContent():
                with TabPane("Urgent", id="tab-urgent"):
                    yield DataTable(id="urgent-table", zebra_stripes=True, classes="panel-table")
                with TabPane("Cases", id="tab-cases"):
                    yield DataTable(id="cases-table", zebra_stripes=True, classes="panel-table")
                with TabPane("Coparent", id="tab-coparent"):
                    yield DataTable(id="coparent-table", zebra_stripes=True, classes="panel-table")
                with TabPane("Bankruptcy", id="tab-bankruptcy"):
                    yield DataTable(id="bankruptcy-table", zebra_stripes=True, classes="panel-table")
                with TabPane("Workers Comp", id="tab-wc"):
                    yield DataTable(id="wc-table", zebra_stripes=True, classes="panel-table")
                with TabPane("Cross-Case", id="tab-cross"):
                    yield DataTable(id="cross-table", zebra_stripes=True, classes="panel-table")
                with TabPane("Session", id="tab-session"):
                    yield DataTable(id="session-table", zebra_stripes=True, classes="panel-table")
            yield Footer()

        def on_mount(self) -> None:
            self.action_refresh()
            for table in self.query(DataTable):
                table.cursor_type = "row"

        @staticmethod
        def _item_key(item: dict) -> str:
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
            return f"{source_db}|{item_type}|{item_id}"

        def _register_item(self, item: dict) -> str:
            key = self._item_key(item)
            self._item_by_key[key] = item
            return key

        def _configure_table(self, table: DataTable) -> None:
            table.cursor_type = "row"

        def _item_from_row_key(self, row_key) -> dict | None:
            key = getattr(row_key, "value", None) or str(row_key)
            return self._item_by_key.get(str(key))

        def _selected_item(self) -> dict | None:
            table = self._active_table()
            if table is None:
                return None
            try:
                cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
                return self._item_from_row_key(cell_key[0])
            except Exception:
                return None

        def _show_detail(self, item: dict) -> None:
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
            if not item_id:
                self.notify("No detail for this row.", severity="warning")
                return
            self.push_screen(DetailScreen(source_db, item_type, item_id))

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            item = self._item_from_row_key(event.row_key)
            if item:
                self._show_detail(item)

        def _add_item_row(self, table: DataTable, item: dict, *cells: str) -> None:
            row_key = self._register_item(item)
            table.add_row(*cells, key=row_key)

        def _active_table(self) -> DataTable | None:
            tab = self.query_one(TabbedContent).active
            mapping = {
                "tab-urgent": "urgent-table",
                "tab-cases": "cases-table",
                "tab-coparent": "coparent-table",
                "tab-bankruptcy": "bankruptcy-table",
                "tab-wc": "wc-table",
                "tab-cross": "cross-table",
                "tab-session": "session-table",
            }
            table_id = mapping.get(tab)
            if not table_id:
                return None
            try:
                return self.query_one(f"#{table_id}", DataTable)
            except Exception:
                return None

        def action_refresh(self) -> None:
            self._item_by_key.clear()
            result = _sync_and_report()
            copied = ", ".join(result["copied"]) or "none"
            missing = ", ".join(result["missing"]) or "none"
            optional = ", ".join(result.get("optional_missing") or []) or "none"
            artifacts = ", ".join(result.get("artifacts") or []) or "none"
            self.query_one("#milestones", Static).update(milestone_banner())
            resolved_label = "showing resolved" if self.show_resolved else "hiding resolved"
            self.query_one("#sync-status", Static).update(
                f"Synced → {result['dest']} | copied: {copied} | missing: {missing} | "
                f"optional: {optional} | artifacts: {artifacts} | {resolved_label} | "
                f"Enter on row or v = detail"
            )
            self._load_urgent()
            self._load_cases()
            self._load_coparent()
            self._load_bankruptcy()
            self._load_workers_comp()
            self._load_cross_case()
            self._load_session()
            table = self._active_table()
            if table is not None:
                table.focus()

        def on_tabbed_content_tab_activated(self, _event) -> None:
            table = self._active_table()
            if table is not None:
                table.focus()

        def action_toggle_resolved(self) -> None:
            self.show_resolved = not self.show_resolved
            self._load_urgent()
            resolved_label = "showing resolved" if self.show_resolved else "hiding resolved"
            status = self.query_one("#sync-status", Static)
            text = str(status.renderable)
            for old in ("showing resolved", "hiding resolved"):
                if old in text:
                    status.update(text.replace(old, resolved_label))
                    break

        def action_open_detail(self) -> None:
            item = self._selected_item()
            if item:
                self._show_detail(item)
            else:
                self.notify("Select a row, then press Enter or v for detail.", severity="information")

        def action_mark_done(self) -> None:
            item = self._selected_item()
            if not item:
                return
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
            if not item_id:
                return
            gazelle_state.mark_resolved(source_db, item_type, item_id)
            self.action_refresh()

        def action_add_note(self) -> None:
            item = self._selected_item()
            if not item:
                return
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")

            def save_note(body: str | None) -> None:
                if body:
                    gazelle_state.add_note(source_db, item_type, item_id, body)
                    self.action_refresh()

            self.push_screen(NoteModal(source_db, item_type, item_id), save_note)

        def action_snooze(self) -> None:
            item = self._selected_item()
            if not item:
                return
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")

            def apply_snooze(until: str | None) -> None:
                if until:
                    gazelle_state.snooze_until(source_db, item_type, item_id, until)
                    self.action_refresh()

            self.push_screen(SnoozeModal(), apply_snooze)

        def action_open_artifact(self) -> None:
            tab = self.query_one(TabbedContent).active
            if tab != "tab-session":
                return
            item = self._selected_item()
            if item and item.get("item_type") == "artifact":
                path = item.get("path")
                if path:
                    subprocess.Popen(
                        ["xdg-open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return
            arts = list_artifacts()
            if not arts:
                return
            path = arts[0]["path"]
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def _load_urgent(self) -> None:
            table = self.query_one("#urgent-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Days", "Case", "Kind", "Severity", "Deadline", "Title")
            items = urgent_queue(show_resolved=self.show_resolved)
            for item in items:
                days = item.get("days_until")
                days_s = str(days) if days is not None else "—"
                if item.get("overdue"):
                    days_s = f"!{days_s}"
                sev = item.get("severity") or item.get("priority") or ""
                title = item.get("title") or item.get("flag_id") or item.get("atom_id") or ""
                dl = item.get("deadline") or ""
                self._add_item_row(
                    table, item,
                    days_s,
                    item.get("case", ""),
                    item.get("kind", ""),
                    sev,
                    str(dl),
                    title[:70],
                )
            self._configure_table(table)

        def _load_cases(self) -> None:
            table = self.query_one("#cases-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Case", "Number", "Status", "Open Items", "Jurisdiction")
            for case in list_cases():
                item = {
                    "source_db": case["key"],
                    "item_type": "case",
                    "item_id": case["key"],
                    **case,
                }
                self._add_item_row(
                    table, item,
                    case["title"],
                    case.get("case_number", ""),
                    case.get("status", ""),
                    str(case.get("open_items", 0)),
                    case.get("jurisdiction", "")[:50],
                )
            self._configure_table(table)

        def _load_coparent(self) -> None:
            table = self.query_one("#coparent-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Priority", "Domain", "Title", "Action")
            for atom in coparent_atoms(status="open"):
                item = {
                    "source_db": "coparent",
                    "item_type": "atom",
                    "item_id": atom["atom_id"],
                    "kind": "atom",
                    **atom,
                }
                self._add_item_row(
                    table, item,
                    atom.get("atom_id", ""),
                    atom.get("priority", ""),
                    atom.get("domain", ""),
                    (atom.get("title") or "")[:60],
                    (atom.get("action_required") or "")[:80],
                )
            self._configure_table(table)

        def _load_bankruptcy(self) -> None:
            table = self.query_one("#bankruptcy-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Type", "Severity/Status", "Item", "Deadline/Notes")
            overview = bankruptcy_overview()
            for case in overview.get("cases") or []:
                table.add_row(
                    "case",
                    case.get("status", ""),
                    f"Ch.{case.get('chapter')} {case.get('case_id')}",
                    (case.get("notes") or "")[:80],
                )
            for flag in overview.get("flags") or []:
                item = {
                    "source_db": "bankruptcy",
                    "item_type": "flag",
                    "item_id": flag["flag_id"],
                    "kind": "flag",
                    **flag,
                }
                self._add_item_row(
                    table, item,
                    "flag",
                    flag.get("severity", ""),
                    flag.get("title", ""),
                    flag.get("deadline") or (flag.get("action_required") or "")[:80],
                )
            for doc in overview.get("checklist") or []:
                table.add_row(
                    "checklist",
                    doc.get("status", ""),
                    doc.get("doc_type", ""),
                    doc.get("priority", ""),
                )
            self._configure_table(table)

        def _load_workers_comp(self) -> None:
            table = self.query_one("#wc-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Priority", "Domain", "Title", "Action")
            if not workers_comp_overview():
                table.add_row(
                    "—",
                    "—",
                    "—",
                    "workers_comp.db not in Nest",
                    "Run: python3 scripts/scaffold_workers_comp.py",
                )
                return
            for atom in workers_comp_atoms(status="open"):
                item = {
                    "source_db": "workers_comp",
                    "item_type": "atom",
                    "item_id": atom["atom_id"],
                    "kind": "atom",
                    **atom,
                }
                self._add_item_row(
                    table, item,
                    atom.get("atom_id", ""),
                    atom.get("priority", ""),
                    atom.get("domain", ""),
                    (atom.get("title") or "")[:60],
                    (atom.get("action_required") or "")[:80],
                )
            self._configure_table(table)

        def _load_cross_case(self) -> None:
            table = self.query_one("#cross-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Type", "Issue/Party", "Bankruptcy", "Coparent/Context")
            overview = cross_case_overview()
            for x in overview.get("intersections") or []:
                item = {
                    "source_db": "bankruptcy",
                    "item_type": "intersection",
                    "item_id": x.get("issue", ""),
                    **x,
                }
                self._add_item_row(
                    table, item,
                    "intersection",
                    (x.get("issue") or "")[:40],
                    (x.get("bankruptcy_impact") or "")[:50],
                    (x.get("coparent_impact") or "")[:50],
                )
            for c in overview.get("creditors") or []:
                item = {
                    "source_db": "bankruptcy",
                    "item_type": "creditor",
                    "item_id": c.get("creditor_id") or str(c.get("id", "")),
                    **c,
                }
                self._add_item_row(
                    table, item,
                    "creditor",
                    c.get("name", ""),
                    c.get("debt_type", ""),
                    f"${c.get('amount_owed') or '—'}",
                )
            for ev in overview.get("context_events") or []:
                item = {
                    "source_db": "coparent",
                    "item_type": "context_event",
                    "item_id": str(ev.get("id", "")),
                    **ev,
                }
                self._add_item_row(
                    table, item,
                    "context",
                    ev.get("event_type", ""),
                    (ev.get("description") or "")[:50],
                    ev.get("effective_date", ""),
                )
            self._configure_table(table)

        def _load_session(self) -> None:
            table = self.query_one("#session-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Type", "Key", "Value")
            overview = session_overview()
            if not overview.get("present"):
                item = {
                    "source_db": "session",
                    "item_type": "session_meta",
                    "item_id": "status",
                    "key": "session_meta.db",
                    "value": "not synced",
                }
                self._add_item_row(table, item, "status", "session_meta.db", "not synced")
                self._configure_table(table)
                return
            for key, value in overview.get("meta", {}).items():
                item = {
                    "source_db": "session",
                    "item_type": "session_meta",
                    "item_id": key,
                    "key": key,
                    "value": value,
                }
                self._add_item_row(table, item, "meta", key, str(value)[:100])
            for art in overview.get("artifacts") or []:
                item = {
                    "source_db": "session",
                    "item_type": "artifact",
                    "item_id": art.get("name", ""),
                    **art,
                }
                self._add_item_row(
                    table, item,
                    "artifact",
                    art.get("name", ""),
                    f"{art.get('size_kb', '?')} KB · o to open",
                )
            for dec in overview.get("decisions") or []:
                decision_id = dec.get("id")
                if decision_id is None:
                    decision_id = (dec.get("decision") or "")[:40]
                item = {
                    "source_db": "session",
                    "item_type": "session_decision",
                    "item_id": str(decision_id),
                    **dec,
                }
                self._add_item_row(
                    table, item,
                    "decision",
                    (dec.get("decision") or "")[:60],
                    (dec.get("rationale") or "")[:100],
                )
            self._configure_table(table)


def _cli_fallback() -> int:
    """Plain-text dashboard when Textual is not installed."""
    result = _sync_and_report()
    print(milestone_banner())
    print(f"Synced → {result['dest']}")
    print(f"  copied:  {', '.join(result['copied']) or 'none'}")
    print(f"  missing: {', '.join(result['missing']) or 'none'}")
    print()

    print("=== URGENT QUEUE ===")
    for item in urgent_queue():
        sev = item.get("severity") or item.get("priority") or "?"
        title = item.get("title") or item.get("flag_id") or item.get("atom_id")
        dl = item.get("deadline") or "—"
        days = item.get("days_until", "—")
        print(f"  [{item.get('case')}] {sev:8} {str(days):>4}d {dl:12} {title}")

    print("\n=== CASES ===")
    for case in list_cases():
        print(f"  {case['title']:28} {case.get('case_number',''):16} {case.get('status','')}")

    print("\n=== CROSS-CASE ===")
    cc = cross_case_overview()
    for x in cc.get("intersections") or []:
        print(f"  {x.get('issue')}")

    wc = workers_comp_overview()
    print("\n=== WORKERS COMP ===")
    if wc is None:
        print("  workers_comp.db not found — run scripts/scaffold_workers_comp.py")
    else:
        for a in wc.get("atoms") or []:
            print(f"  {a.get('atom_id')}: {a.get('title')}")

    session = session_overview()
    print("\n=== SESSION ===")
    if not session.get("present"):
        print("  session_meta.db not synced")
    else:
        for key in (
            "session_date", "session_outcome", "letter_sent",
            "response_deadline_1", "response_deadline_2",
        ):
            if key in session.get("meta", {}):
                print(f"  {key}: {session['meta'][key]}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Law Gazelle case command center")
    parser.add_argument("--sync-only", action="store_true", help="Sync databases and exit")
    parser.add_argument("--source", type=Path, default=Path.home() / "Desktop" / "Nest")
    args = parser.parse_args()

    result = sync_cases(args.source)
    if args.sync_only:
        print(json_dump(result))
        return 0

    if App is None:
        return _cli_fallback()

    app = LawGazelleApp()
    app.run()
    return 0


def json_dump(obj: dict) -> str:
    import json
    return json.dumps(obj, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
