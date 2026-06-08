"""
Story Timeline v2 — literary knowledge base.
Open node graph: books, authors, notes, themes, projects — all connected.

Usage:
  python3 app.py            → TUI
  textual serve app.py      → same app in browser
"""
import sys
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label,
    ListItem, ListView, Markdown, Select, Static, TabbedContent,
    TabPane, TextArea, Tree,
)

import timeline_db as db
import willow_edges
import safe_integration
import migrate


# ── Helpers ───────────────────────────────────────────────────────────────────

_STARS = {0: "—", 1: "★", 2: "★★", 3: "★★★", 4: "★★★★", 5: "★★★★★"}
_SHELF_LABEL = {
    "read": "Read",
    "currently-reading": "Reading",
    "to-read": "To Read",
    "dnf": "DNF",
}

LITERARY_TYPES = (
    "book", "author", "note", "project", "theme", "character", "place", "event",
)

ENTITY_TEMPLATES = {
    "book": "title: \nauthor: \nshelf: to-read\nrating: 0\ntags: \nreview: ",
    "author": "name: \nnotes: ",
    "note": "title: \ncontent: \ntags: ",
    "project": "title: \nstatus: planning\nsummary: ",
    "theme": "name: \nnotes: ",
    "character": "name: \nrole: \nnotes: ",
    "place": "name: \ndescription: ",
    "event": "title: \nworld_date: \nsummary: ",
}


def _stars(rating) -> str:
    try:
        return _STARS.get(int(rating), "—")
    except (ValueError, TypeError):
        return "—"


def _shelf_label(shelf: str) -> str:
    return _SHELF_LABEL.get(shelf, shelf or "—")


def _node_title(node: dict) -> str:
    f = node.get("fields", {})
    return (
        f.get("title") or f.get("name") or
        str(f.get("summary", ""))[:40] or
        node["type"]
    )


# ── Boot ──────────────────────────────────────────────────────────────────────

def boot_sequence(uuid: Optional[str] = None) -> dict:
    result = {"migrated": 0, "orphans_removed": 0}
    if migrate.needs_migration():
        result["migrated"] = migrate.run_migration()
    node_ids = db.get_all_node_ids()
    result["orphans_removed"] = willow_edges.reconcile_orphans(node_ids, uuid=uuid)
    return result


# ── Screens ───────────────────────────────────────────────────────────────────

class NodePickerScreen(ModalScreen):
    """Searchable node picker — replaces UUID paste for linking."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Select target node", id="modal-title"),
            Input(placeholder="search by title, name, type…", id="picker-search"),
            ListView(id="picker-list"),
            Button("Cancel", id="cancel-btn"),
            id="modal-content",
        )

    def on_mount(self) -> None:
        self._all_nodes = db.get_nodes()
        self._visible: list[dict] = []
        self._refresh_list(self._all_nodes)
        self.query_one("#picker-search", Input).focus()

    def _refresh_list(self, nodes: list) -> None:
        lv = self.query_one("#picker-list", ListView)
        lv.clear()
        self._visible = nodes[:60]
        for node in self._visible:
            lv.append(ListItem(Label(f"[{node['type']}]  {_node_title(node)}")))

    def on_input_changed(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        if not q:
            self._refresh_list(self._all_nodes)
        else:
            self._refresh_list([
                n for n in self._all_nodes
                if q in _node_title(n).lower() or q in n["type"].lower()
            ])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one("#picker-list", ListView).index
        if idx is not None and 0 <= idx < len(self._visible):
            self.dismiss(self._visible[idx]["id"])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class RelationScreen(ModalScreen):
    """Enter relation label after picking a target node."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, from_id: str, to_id: str):
        super().__init__()
        self._from_id = from_id
        self._to_id = to_id

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Relation label", id="modal-title"),
            Label(f"…{self._from_id[-12:]}  →  …{self._to_id[-12:]}"),
            Input(placeholder="written_by / knows / inspired / set_in / …", id="relation-input"),
            Horizontal(
                Button("Link", variant="primary", id="link-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_mount(self) -> None:
        self.query_one("#relation-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        relation = self.query_one("#relation-input", Input).value.strip()
        if relation:
            self.dismiss(relation)


class ImportScreen(ModalScreen):
    """CSV import — Goodreads / StoryGraph / LibraryThing."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Import from CSV", id="modal-title"),
            Label("File path (Goodreads / StoryGraph / LibraryThing export):"),
            Input(placeholder="~/Downloads/goodreads_library_export.csv", id="path-input"),
            Label("Source — leave blank to auto-detect:"),
            Input(placeholder="goodreads / storygraph / librarything", id="source-input"),
            Horizontal(
                Button("Import", variant="primary", id="import-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        path_str = self.query_one("#path-input", Input).value.strip()
        source = self.query_one("#source-input", Input).value.strip() or None
        self.dismiss({"path": path_str, "source": source} if path_str else None)


class CreateNodeScreen(ModalScreen):
    """Create or edit a node."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, node: Optional[dict] = None, default_type: str = "book"):
        super().__init__()
        self._node = node
        self._default_type = default_type

    def compose(self) -> ComposeResult:
        existing_type = self._node["type"] if self._node else self._default_type
        existing_fields = ""
        if self._node:
            f = self._node.get("fields", {})
            existing_fields = "\n".join(f"{k}: {v}" for k, v in f.items())
        else:
            existing_fields = ENTITY_TEMPLATES.get(existing_type, "")
        widgets = [
            Label("Edit Node" if self._node else "Create Node", id="modal-title"),
        ]
        if not self._node:
            type_opts = [(t, t) for t in LITERARY_TYPES]
            widgets += [
                Label("Template"),
                Select(type_opts, id="template-select", value=existing_type),
            ]
        widgets += [
            Label("Type  (book / author / note / theme / project / …)"),
            Input(value=existing_type, id="type-input"),
            Label("Fields — one  key: value  per line"),
            TextArea(existing_fields, id="fields-input"),
            Horizontal(
                Button("Save", variant="primary", id="save-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
        ]
        yield Vertical(*widgets, id="modal-content")

    def on_mount(self) -> None:
        if self._node:
            self.query_one("#type-input", Input).focus()
        else:
            self.query_one("#template-select", Select).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "template-select":
            return
        type_ = str(event.value)
        self.query_one("#type-input", Input).value = type_
        fields = self.query_one("#fields-input", TextArea)
        if not fields.text.strip():
            fields.text = ENTITY_TEMPLATES.get(type_, "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        type_ = self.query_one("#type-input", Input).value.strip()
        if not type_:
            return
        raw = self.query_one("#fields-input", TextArea).text.strip()
        fields: dict = {}
        for line in raw.splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                fields[k.strip()] = v.strip()
        self.dismiss({"type": type_, "fields": fields})


class NodeDetailScreen(ModalScreen):
    """Rich node detail — fields, edges, review rendered as Markdown."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, node: dict, edges: list):
        super().__init__()
        self._node = node
        self._edges = edges

    def _build_md(self) -> str:
        f = self._node.get("fields", {})
        title = f.get("title") or f.get("name") or self._node["type"]
        lines = [f"# {title}", ""]
        if f.get("author"):
            lines.append(f"**Author:** {f['author']}")
        rating = _stars(f.get("rating", 0))
        if rating != "—":
            lines.append(f"**Rating:** {rating}")
        shelf = _shelf_label(f.get("shelf", ""))
        if shelf and shelf != "—":
            lines.append(f"**Shelf:** {shelf}")
        for k, v in f.items():
            if k not in ("title", "author", "rating", "shelf", "review", "name"):
                lines.append(f"**{k}:** {v}")
        if self._edges:
            lines += ["", "---", "", "**Connections:**", ""]
            for e in self._edges:
                if e["from_id"] == self._node["id"]:
                    lines.append(f"- → `{e['relation']}` → `{e['to_id'][:20]}`")
                else:
                    lines.append(f"- ← `{e['relation']}` ← `{e['from_id'][:20]}`")
        review = f.get("review", "").strip()
        if review:
            lines += ["", "---", "", review]
        return "\n".join(lines)

    def compose(self) -> ComposeResult:
        yield Vertical(
            Markdown(self._build_md(), id="detail-md"),
            Button("Close", id="close-btn"),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


# ── Main App ──────────────────────────────────────────────────────────────────

class LibraryApp(App):
    CSS = """
    /* Modals */
    CreateNodeScreen, NodePickerScreen, NodeDetailScreen,
    ImportScreen, RelationScreen { align: center middle; }

    #modal-content {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 80;
        height: auto;
        max-height: 90vh;
    }
    NodeDetailScreen #modal-content { width: 90; }
    #modal-title { text-style: bold; margin-bottom: 1; }
    #detail-md { height: 30; border: solid $surface-lighten-2; padding: 0 1; }
    #picker-list { height: 14; border: solid $surface-lighten-2; }

    /* Layout */
    #books-layout { height: 1fr; }
    #sidebar { width: 24; border-right: solid $surface-lighten-1; padding: 0 1; }
    #sidebar-heading { text-style: bold; color: $text-muted; margin-bottom: 1; }
    #content-panel { width: 1fr; }
    #search-input { width: 1fr; }
    #node-table { height: 1fr; }
    #status { height: 1; color: $text-muted; padding: 0 1; }
    #author-table, #notes-table, #all-table { height: 1fr; }
    """

    BINDINGS = [
        Binding("a", "add_node", "Add"),
        Binding("e", "edit_node", "Edit"),
        Binding("d", "delete_node", "Delete"),
        Binding("l", "link_node", "Link"),
        Binding("v", "view_node", "View"),
        Binding("i", "import_csv", "Import"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, uuid: Optional[str] = None):
        super().__init__()
        self._uuid = uuid
        self._book_ids: list[str] = []
        self._author_ids: list[str] = []
        self._note_ids: list[str] = []
        self._all_ids: list[str] = []
        self._shelf_filter: Optional[str] = None
        self._tag_filter: Optional[str] = None
        self._search: Optional[str] = None
        self._link_target: str = ""
        self._stats = {"nodes_created": 0, "edges_created": 0}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("Books", id="tab-books"):
                yield Horizontal(
                    Vertical(
                        Label("LIBRARY", id="sidebar-heading"),
                        Tree("All", id="shelf-tree"),
                        id="sidebar",
                    ),
                    Vertical(
                        Input(placeholder="search…", id="search-input"),
                        DataTable(id="node-table", cursor_type="row"),
                        Static("", id="status"),
                        id="content-panel",
                    ),
                    id="books-layout",
                )
            with TabPane("Authors", id="tab-authors"):
                yield DataTable(id="author-table", cursor_type="row")
            with TabPane("Notes", id="tab-notes"):
                yield DataTable(id="notes-table", cursor_type="row")
            with TabPane("All Nodes", id="tab-all"):
                yield DataTable(id="all-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Story Timeline"
        self.sub_title = "literary knowledge base"
        self._rebuild_shelf_tree()
        self._rebuild_books_table()
        self._rebuild_author_table()
        self._rebuild_notes_table()
        self._rebuild_all_table()

    # ── Shelf tree ────────────────────────────────────────────────────────────

    def _rebuild_shelf_tree(self) -> None:
        tree = self.query_one("#shelf-tree", Tree)
        tree.clear()
        books = db.get_nodes(type_="book")

        shelf_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        for b in books:
            shelf = b["fields"].get("shelf", "")
            if shelf:
                shelf_counts[shelf] = shelf_counts.get(shelf, 0) + 1
            for tag in b["fields"].get("tags", "").split(","):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        root = tree.root
        root.expand()
        root.add_leaf(f"All books  ({len(books)})", data={"filter": "all"})

        if shelf_counts:
            shelves = root.add("Shelves", data=None)
            for shelf in ("read", "currently-reading", "to-read", "dnf"):
                count = shelf_counts.get(shelf, 0)
                if count:
                    shelves.add_leaf(
                        f"{_shelf_label(shelf)}  ({count})",
                        data={"filter": "shelf", "value": shelf},
                    )
            shelves.expand()

        if tag_counts:
            tags_node = root.add("Tags", data=None)
            for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])[:20]:
                tags_node.add_leaf(f"{tag}  ({count})", data={"filter": "tag", "value": tag})

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return
        f = data.get("filter")
        if f == "all":
            self._shelf_filter = None
            self._tag_filter = None
        elif f == "shelf":
            self._shelf_filter = data["value"]
            self._tag_filter = None
        elif f == "tag":
            self._shelf_filter = None
            self._tag_filter = data["value"]
        else:
            return
        self._search = None
        self.query_one("#search-input", Input).value = ""
        self._rebuild_books_table()

    # ── Books table ───────────────────────────────────────────────────────────

    def _rebuild_books_table(self) -> None:
        table = self.query_one("#node-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Title", "Author", "Rating", "Shelf", "Date Read")

        if self._search:
            nodes = [n for n in db.search_nodes(self._search) if n["type"] == "book"]
        elif self._shelf_filter:
            nodes = [
                n for n in db.get_nodes(type_="book")
                if n["fields"].get("shelf") == self._shelf_filter
            ]
        elif self._tag_filter:
            tag = self._tag_filter
            nodes = [
                n for n in db.get_nodes(type_="book")
                if tag in [t.strip() for t in n["fields"].get("tags", "").split(",")]
            ]
        else:
            nodes = db.get_nodes(type_="book")

        self._book_ids = [n["id"] for n in nodes]
        for n in nodes:
            f = n["fields"]
            table.add_row(
                f.get("title", "—")[:52],
                f.get("author", "—")[:28],
                _stars(f.get("rating", 0)),
                _shelf_label(f.get("shelf", "")),
                (f.get("date_read") or "")[:10],
            )

        parts = [f"{len(nodes)} book(s)"]
        if self._shelf_filter:
            parts.append(f"shelf={_shelf_label(self._shelf_filter)}")
        if self._tag_filter:
            parts.append(f"tag={self._tag_filter}")
        if self._search:
            parts.append(f"search='{self._search}'")
        self.query_one("#status", Static).update("  ".join(parts))

    # ── Other tabs ────────────────────────────────────────────────────────────

    def _rebuild_author_table(self) -> None:
        table = self.query_one("#author-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Notes")
        authors = db.get_nodes(type_="author")
        self._author_ids = [a["id"] for a in authors]
        for a in authors:
            f = a["fields"]
            table.add_row(f.get("name", "—"), f.get("notes", "")[:60])

    def _rebuild_notes_table(self) -> None:
        table = self.query_one("#notes-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Title", "Preview")
        notes = db.get_nodes(type_="note")
        self._note_ids = [n["id"] for n in notes]
        for n in notes:
            f = n["fields"]
            title = f.get("title") or f.get("name") or "—"
            preview = f.get("content") or f.get("summary") or ""
            table.add_row(title[:50], preview[:70])

    def _rebuild_all_table(self) -> None:
        table = self.query_one("#all-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Type", "Summary", "ID")
        nodes = db.get_nodes()
        self._all_ids = [n["id"] for n in nodes]
        for n in nodes:
            table.add_row(n["type"], _node_title(n)[:60], n["id"][:16] + "…")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._rebuild_shelf_tree()
        self._rebuild_books_table()
        self._rebuild_author_table()
        self._rebuild_notes_table()
        self._rebuild_all_table()

    def _selected_from_table(self, table_id: str, ids: list[str]) -> Optional[dict]:
        table = self.query_one(table_id, DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(ids):
            return None
        return db.get_node(ids[row])

    def _selected_node(self) -> Optional[dict]:
        tab = self._active_tab()
        if tab == "tab-books":
            return self._selected_from_table("#node-table", self._book_ids)
        if tab == "tab-authors":
            return self._selected_from_table("#author-table", self._author_ids)
        if tab == "tab-notes":
            return self._selected_from_table("#notes-table", self._note_ids)
        if tab == "tab-all":
            return self._selected_from_table("#all-table", self._all_ids)
        return None

    def _active_tab(self) -> str:
        try:
            return str(self.query_one("#tabs", TabbedContent).active)
        except Exception:
            return "tab-books"

    def _default_type_for_tab(self) -> str:
        return {"tab-authors": "author", "tab-notes": "note"}.get(self._active_tab(), "book")

    # ── Input handler ─────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._search = event.value.strip() or None
            self._shelf_filter = None
            self._tag_filter = None
            self._rebuild_books_table()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_add_node(self) -> None:
        def on_dismiss(result):
            if result:
                db.add_node(type_=result["type"], fields=result["fields"])
                self._stats["nodes_created"] += 1
                self._refresh_all()
                self.notify(f"Added {result['type']}.")
        self.push_screen(CreateNodeScreen(default_type=self._default_type_for_tab()), on_dismiss)

    def action_edit_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        def on_dismiss(result):
            if result:
                db.update_node(node["id"], fields=result["fields"])
                self._refresh_all()
                self.notify("Updated.")
        self.push_screen(CreateNodeScreen(node=node), on_dismiss)

    def action_delete_node(self) -> None:
        node = self._selected_node()
        if node and db.delete_node(node["id"]):
            self._refresh_all()
            self.notify("Deleted.")

    def action_link_node(self) -> None:
        node = self._selected_node()
        if not node:
            return

        def on_relation(relation: Optional[str]) -> None:
            if relation:
                willow_edges.add_edge(
                    node["id"], self._link_target, relation, uuid=self._uuid
                )
                self._stats["edges_created"] += 1
                self.notify(f"Linked: {relation}")

        def on_picker(target_id: Optional[str]) -> None:
            if target_id:
                self._link_target = target_id
                self.push_screen(
                    RelationScreen(from_id=node["id"], to_id=target_id), on_relation
                )

        self.push_screen(NodePickerScreen(), on_picker)

    def action_view_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        edges = willow_edges.edges_for(node["id"], uuid=self._uuid)
        self.push_screen(NodeDetailScreen(node=node, edges=edges))

    def action_import_csv(self) -> None:
        def on_dismiss(result):
            if not result:
                return
            path = Path(result["path"]).expanduser()
            if not path.exists():
                self.notify(f"Not found: {path}", severity="error")
                return
            import import_csv
            r = import_csv.run_import(
                path,
                source=result.get("source"),
                create_authors=True,
                uuid=self._uuid,
            )
            self._refresh_all()
            msg = (
                f"Imported {r['imported']} · Skipped {r['skipped']} · "
                f"Errors {r['errors']} · Authors {r.get('author_nodes', 0)}"
            )
            self.notify(msg)
        self.push_screen(ImportScreen(), on_dismiss)

    def action_focus_search(self) -> None:
        try:
            self.query_one("#search-input", Input).focus()
        except Exception:
            pass

    def action_refresh(self) -> None:
        self._refresh_all()
        self.notify("Refreshed.")

    def action_quit(self) -> None:
        if self._uuid:
            safe_integration.write_session_composite(
                stats={**self._stats, "types_used": []}, uuid=self._uuid
            )
        self.exit()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uuid = safe_integration.get_user_uuid()
    if not uuid:
        sys.stderr.write(
            "Warning: ~/.willow/user_identity.json not found — Willow edges disabled.\n\n"
        )
    boot = boot_sequence(uuid=uuid)
    if boot["migrated"]:
        print(f"Migrated {boot['migrated']} v1 event(s).")
    LibraryApp(uuid=uuid).run()
