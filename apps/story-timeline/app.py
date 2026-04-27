"""
Story Timeline v2 — open node graph writing tool.
Professor Oakenscroll's successor. Local. Free. Willow-integrated.

Usage:
  python3 app.py          → TUI
  python3 app.py --web    → web server + open browser
"""
import json
import sys
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable, Footer, Header, Input, Label,
    Button, Select, Static, TextArea
)

import timeline_db as db
import willow_edges
import safe_integration
import migrate


# ── Boot ──────────────────────────────────────────────────────────────────────

def boot_sequence(uuid: Optional[str] = None) -> dict:
    import sys as _sys
    _migrate = _sys.modules.get("migrate", migrate)
    _db = _sys.modules.get("timeline_db", db)
    _edges = _sys.modules.get("willow_edges", willow_edges)
    result = {"migrated": 0, "orphans_removed": 0, "uuid": uuid}
    if _migrate.needs_migration():
        result["migrated"] = _migrate.run_migration()
    node_ids = _db.get_all_node_ids()
    result["orphans_removed"] = _edges.reconcile_orphans(node_ids, uuid=uuid)
    return result


# ── Screens ───────────────────────────────────────────────────────────────────

class CreateNodeScreen(ModalScreen):
    """Create or edit a node. Fields entered as 'key: value' lines."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, node: Optional[dict] = None):
        super().__init__()
        self._node = node

    def compose(self) -> ComposeResult:
        existing_type = self._node["type"] if self._node else ""
        existing_fields = ""
        if self._node:
            fields = self._node.get("fields", {})
            if isinstance(fields, str):
                fields = json.loads(fields)
            existing_fields = "\n".join(f"{k}: {v}" for k, v in fields.items())
        yield Vertical(
            Label("Create Node" if not self._node else "Edit Node", id="modal-title"),
            Label("Entity type (e.g. character, location, event)"),
            Input(value=existing_type, placeholder="character", id="type-input"),
            Label("Fields — one 'key: value' per line"),
            TextArea(existing_fields, id="fields-input"),
            Horizontal(
                Button("Save", variant="primary", id="save-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        type_ = self.query_one("#type-input", Input).value.strip()
        if not type_:
            return
        raw = self.query_one("#fields-input", TextArea).text.strip()
        fields = {}
        for line in raw.splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                fields[k.strip()] = v.strip()
        self.dismiss({"type": type_, "fields": fields})


class LinkNodesScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, from_id: str):
        super().__init__()
        self._from_id = from_id

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Link Nodes", id="modal-title"),
            Label(f"From: {self._from_id[:24]}"),
            Label("Target node ID (paste full ID)"),
            Input(placeholder="paste node ID", id="to-id"),
            Label("Relation label"),
            Input(placeholder="knows / causes / located_in", id="relation"),
            Horizontal(
                Button("Link", variant="primary", id="link-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        to_id = self.query_one("#to-id", Input).value.strip()
        relation = self.query_one("#relation", Input).value.strip()
        if not to_id or not relation:
            return
        self.dismiss({"from_id": self._from_id, "to_id": to_id, "relation": relation})


class NodeDetailScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, node: dict, edges: list):
        super().__init__()
        self._node = node
        self._edges = edges

    def compose(self) -> ComposeResult:
        fields = self._node.get("fields", {})
        if isinstance(fields, str):
            fields = json.loads(fields)
        fields_text = "\n".join(f"  {k}: {v}" for k, v in fields.items()) or "  (no fields)"
        if self._edges:
            edges_text = "\n".join(
                f"  → {e['relation']} → {e['to_id'][:20]}" if e["from_id"] == self._node["id"]
                else f"  ← {e['relation']} ← {e['from_id'][:20]}"
                for e in self._edges
            )
        else:
            edges_text = "  (no edges)"
        yield Vertical(
            Label(f"[{self._node['type']}]", id="modal-title"),
            Label("Fields:"),
            Static(fields_text),
            Label("Edges:"),
            Static(edges_text),
            Button("Close", id="close-btn"),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


# ── Main App ──────────────────────────────────────────────────────────────────

class TimelineApp(App):
    CSS = """
    #modal-content {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 72;
        height: auto;
        max-height: 90vh;
    }
    #modal-title { text-style: bold; margin-bottom: 1; }
    CreateNodeScreen, LinkNodesScreen, NodeDetailScreen { align: center middle; }
    #filter-bar { height: 3; }
    #type-select { width: 24; }
    #search-input { width: 1fr; }
    #status { height: 1; color: $text-muted; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("a", "create_node", "Add"),
        Binding("e", "edit_node", "Edit"),
        Binding("d", "delete_node", "Delete"),
        Binding("l", "link_node", "Link"),
        Binding("v", "view_node", "View"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, uuid: Optional[str] = None):
        super().__init__()
        self._uuid = uuid
        self._type_filter: Optional[str] = None
        self._search: Optional[str] = None
        self._node_ids: list[str] = []
        self._stats = {"nodes_created": 0, "edges_created": 0, "types_used": set()}

    def compose(self) -> ComposeResult:
        types = db.get_types()
        type_opts = [("All types", "__all__")] + [(t, t) for t in types]
        yield Header(show_clock=True)
        yield Horizontal(
            Label("Type: "),
            Select(type_opts, id="type-select", value="__all__"),
            Input(placeholder="search…", id="search-input"),
            id="filter-bar",
        )
        yield DataTable(id="node-table")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Story Timeline v2"
        self.sub_title = "open node graph"
        self._build_table()

    def _node_summary(self, node: dict) -> str:
        fields = node.get("fields", {})
        if isinstance(fields, str):
            fields = json.loads(fields)
        return (
            fields.get("name") or
            fields.get("title") or
            str(fields.get("summary", ""))[:50] or
            node["type"]
        )

    def _build_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("ID", "Type", "Summary")
        nodes = db.search_nodes(self._search) if self._search else db.get_nodes(type_=self._type_filter)
        self._node_ids = [n["id"] for n in nodes]
        for n in nodes:
            table.add_row(n["id"][:16] + "…", n["type"], self._node_summary(n))
        self.query_one("#status", Static).update(
            f"{len(nodes)} node(s)"
            + (f"  type={self._type_filter}" if self._type_filter else "")
            + (f"  search='{self._search}'" if self._search else "")
        )

    def _selected_node(self) -> Optional[dict]:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._node_ids):
            return None
        return db.get_node(self._node_ids[row])

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "type-select":
            self._type_filter = None if event.value == "__all__" else str(event.value)
            self._build_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._search = event.value.strip() or None
            self._build_table()

    def action_create_node(self) -> None:
        def on_dismiss(result):
            if result:
                db.add_node(type_=result["type"], fields=result["fields"])
                self._stats["nodes_created"] += 1
                self._stats["types_used"].add(result["type"])
                self._build_table()
        self.push_screen(CreateNodeScreen(), on_dismiss)

    def action_edit_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        def on_dismiss(result):
            if result:
                db.update_node(node["id"], fields=result["fields"])
                self._build_table()
        self.push_screen(CreateNodeScreen(node=node), on_dismiss)

    def action_delete_node(self) -> None:
        node = self._selected_node()
        if node and db.delete_node(node["id"]):
            self._build_table()

    def action_link_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        def on_dismiss(result):
            if result:
                willow_edges.add_edge(
                    result["from_id"], result["to_id"],
                    result["relation"], uuid=self._uuid
                )
                self._stats["edges_created"] += 1
        self.push_screen(LinkNodesScreen(from_id=node["id"]), on_dismiss)

    def action_view_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        edges = willow_edges.edges_for(node["id"], uuid=self._uuid)
        self.push_screen(NodeDetailScreen(node=node, edges=edges))

    def action_refresh(self) -> None:
        self._build_table()

    def action_quit(self) -> None:
        stats = {
            "nodes_created": self._stats["nodes_created"],
            "edges_created": self._stats["edges_created"],
            "types_used": list(self._stats["types_used"]),
        }
        if self._uuid:
            safe_integration.write_session_composite(stats=stats, uuid=self._uuid)
        self.exit()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import web as _web

    uuid = safe_integration.get_user_uuid()
    if not uuid:
        sys.stderr.write(
            "Warning: ~/.willow/user_identity.json not found — Willow edges disabled.\n"
            "Install willow-seed to enable graph persistence.\n\n"
        )

    boot = boot_sequence(uuid=uuid)
    if boot["migrated"]:
        print(f"Migrated {boot['migrated']} v1 event(s) to v2 nodes.")
    if boot["orphans_removed"]:
        print(f"Removed {boot['orphans_removed']} orphan edge(s).")

    if "--web" in sys.argv:
        _web._set_user_uuid(uuid)
        _web.run_web(port=8765)
    else:
        TimelineApp(uuid=uuid).run()
