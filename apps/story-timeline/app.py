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
import story_protocol as proto
import intelligence
import suggestion_store as suggestions
import export_lists
import mcp_client


# ── Help text ─────────────────────────────────────────────────────────────────

HELP_MD = """\
# Story Timeline — Help

## Library (Books · Notes · All Nodes)
| Key | Action |
|-----|--------|
| **a** | Add book, author, note, or library project |
| **e** | Edit selected |
| **d** | Delete selected |
| **l** | Link to another node |
| **v** | View detail |
| **i** | Import CSV (Goodreads / StoryGraph) |
| **o** | Export library trip list + Goodreads CSV |
| **/** | Focus search (Books tab) |
| **j** | Research selected book/note (Jeles) |
| **s** | Suggest promotion (SLM proposal) |
| **p** | Promote selected to a timeline |

## Writing
| Key | Action |
|-----|--------|
| **a** | New writing project, timeline, or hint to promote |
| Select rows | Project → Timeline → Entries |
| **p** | Promote a library item into a timeline |

## Intelligence
| Key | Action |
|-----|--------|
| **j** | Research selected library item |
| **s** | Suggest similar works (book) or project reading list (library project) |
| **v** | Review suggestion or view research (Intelligence tab) |
| **Enter** | Add recommended work to to-read or accept promotion |
| **d** | Dismiss pending suggestion (Intelligence tab) |

**p** promotes selected material into a writing timeline.

## Navigation
Desk · Shelves · Authors · Commonplace · Timelines · Jeles Inbox · Constellation

**r** Refresh · **h** / **?** Help · **q** Quit
"""

_STARS = {0: "—", 1: "★", 2: "★★", 3: "★★★", 4: "★★★★", 5: "★★★★★"}
_SHELF_LABEL = {
    "read": "Read",
    "currently-reading": "Reading",
    "to-read": "To Read",
    "dnf": "DNF",
}
_SHELF_GLYPH = {
    "read": "◉",
    "currently-reading": "◐",
    "to-read": "◎",
    "dnf": "✕",
    "": "·",
}
_TYPE_GLYPH = {
    "book": "◈",
    "author": "✒",
    "note": "✎",
    "project": "◇",
    "writing_project": "◆",
    "timeline": "〜",
    "timeline_entry": "▸",
    "theme": "✦",
    "character": "☉",
    "place": "⌂",
    "event": "⚡",
    "slm_suggestion": "?",
    "research_packet": "⌁",
}
_TAB_CRUMB = {
    "tab-home": "Desk",
    "tab-books": "Shelves",
    "tab-authors": "Authors",
    "tab-notes": "Commonplace",
    "tab-writing": "Timelines",
    "tab-intelligence": "Jeles Inbox",
    "tab-all": "Constellation",
}
_EMPTY_VOICES = {
    "books": "The shelves are bare. Import a CSV or press a to add your first book.",
    "authors": "No authors yet — they'll appear when you import, or press a.",
    "notes": "Commonplace is empty. Capture a quote, idea, or research scrap with a.",
    "writing": "No timelines yet. Pick a note and press p to make it dangerous.",
    "entries": "This lane is quiet. Promote a note or book into a beat.",
    "intelligence": "Jeles has nothing queued. Select a book and press j or s.",
    "constellation": "The sky is empty. Add nodes and link them into constellations.",
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


def _shelf_glyph(shelf: str) -> str:
    return _SHELF_GLYPH.get(shelf, _SHELF_GLYPH[""])


def _type_glyph(node_type: str) -> str:
    return _TYPE_GLYPH.get(node_type, "·")


def _willow_pulse() -> str:
    if mcp_client.available():
        return "[bold #c9a227]Willow awake[/] · Jeles · KB · SLM"
    err = mcp_client.last_error() or "offline"
    return f"[dim]Willow sleeping[/] · {err[:48]}"


def _node_title(node: dict) -> str:
    f = node.get("fields", {})
    return (
        f.get("title") or f.get("name") or
        str(f.get("summary", ""))[:40] or
        node["type"]
    )


def _short_label(value: str, limit: int = 34) -> str:
    value = value.strip() or "selected source"
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _desk_banner() -> str:
    return (
        "[bold #c9a227]✦  S T O R Y   T I M E L I N E  ✦[/]\n"
        "[dim italic]enchanted archive · reading becomes story material[/]"
    )


def _format_home_map(counts: dict[str, int], *, ready: bool) -> str:
    loose = counts["pending_suggestions"]
    research = counts["research_packets"]
    loose_line = (
        f"[bold #e8b86d]{loose} loose thread(s)[/] waiting in Jeles Inbox"
        if loose
        else "[dim]No loose threads — Jeles Inbox is clear[/]"
    )
    river = (
        f"[bold]{counts['writing_projects']} project(s)[/] · "
        f"{counts['timelines']} lane(s) · {counts['timeline_entries']} beat(s)"
        if counts["writing_projects"]
        else "[yellow]The river hasn't started[/] — promote a note to open a lane"
    )
    setup = (
        "[dim]Timelines ready · press p to promote to canon[/]"
        if ready
        else "[yellow]Set up your first timeline[/] — p on any note or book"
    )
    return (
        f"{_desk_banner()}\n\n"
        "[bold underline]On the desk[/]\n"
        f"  ◈ Shelves ··········· {counts['books']} book(s) · "
        f"{counts['authors']} author(s)\n"
        f"  ✎ Commonplace ······· {counts['notes']} scrap(s) · "
        f"{counts['library_projects']} library project(s)\n"
        f"  〜 Timelines ········ {counts['writing_projects']} · "
        f"{counts['timelines']} lane(s) · {counts['timeline_entries']} beat(s)\n"
        f"  ⌁ Research stack ···· {research} packet(s)\n\n"
        "[bold underline]The river[/]\n"
        f"  {river}\n"
        f"  {setup}\n\n"
        "[bold underline]Loose threads[/]\n"
        f"  {loose_line}\n\n"
        "[dim]i import shelf · o export trip list · j ask Jeles · s suggest to-read · "
        "p promote to canon · h for keys[/]"
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
            Label("Find another star in the constellation", id="modal-title"),
            Input(placeholder="search by title, name, kind…", id="picker-search"),
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
            Label("Stock the shelves from CSV", id="modal-title"),
            Label("Path to Goodreads / StoryGraph / LibraryThing export:"),
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


class ExportListScreen(ModalScreen):
    """Choose which portable book list to export."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, *, has_source: bool = False, source_label: str = ""):
        super().__init__()
        self._has_source = has_source
        self._source_label = source_label

    def compose(self) -> ComposeResult:
        options = [
            ("To Read shelf", "to-read"),
            ("All books", "all"),
        ]
        if self._has_source:
            options.append((f"Pending suggestions for {_short_label(self._source_label)}", "selected-source"))
        yield Vertical(
            Label("Pack a trip list", id="modal-title"),
            Label("Markdown library list + Goodreads-style CSV for the road."),
            Label("Scope"),
            Select(options, id="export-scope", value="to-read"),
            Label("Label"),
            Input(value="to-read", id="export-label"),
            Horizontal(
                Button("Export", variant="primary", id="export-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "export-scope":
            return
        labels = {
            "to-read": "to-read",
            "all": "all-books",
            "selected-source": self._source_label or "selected-source",
        }
        self.query_one("#export-label", Input).value = labels.get(str(event.value), "books")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        scope = str(self.query_one("#export-scope", Select).value or "to-read")
        label = self.query_one("#export-label", Input).value.strip() or scope
        self.dismiss({"scope": scope, "label": label})


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
            Label("Type  (book / author / note / project / …)"),
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


class CreateProjectScreen(ModalScreen):
    """Create a writing project."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("New writing project", id="modal-title"),
            Label("Title"),
            Input(placeholder="My novel", id="title-input"),
            Label("Summary"),
            Input(placeholder="optional", id="summary-input"),
            Horizontal(
                Button("Create", variant="primary", id="create-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_mount(self) -> None:
        self.query_one("#title-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            return
        summary = self.query_one("#summary-input", Input).value.strip()
        self.dismiss({"title": title, "summary": summary})


class CreateTimelineScreen(ModalScreen):
    """Create a named timeline under a writing project."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, project_id: str, project_title: str):
        super().__init__()
        self._project_id = project_id
        self._project_title = project_title

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("New timeline", id="modal-title"),
            Label(f"Project: {self._project_title}"),
            Label("Name"),
            Input(placeholder="World chronology", id="name-input"),
            Label("Kind (world / draft / process)"),
            Input(value="world", id="kind-input"),
            Horizontal(
                Button("Create", variant="primary", id="create-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            return
        kind = self.query_one("#kind-input", Input).value.strip() or "world"
        self.dismiss({"project_id": self._project_id, "name": name, "kind": kind})


class TimelinePickerScreen(ModalScreen):
    """Pick a timeline for promotion."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Promote to timeline", id="modal-title"),
            ListView(id="timeline-list"),
            Button("Cancel", id="cancel-btn"),
            id="modal-content",
        )

    def on_mount(self) -> None:
        self._options: list[tuple[dict, dict]] = []
        lv = self.query_one("#timeline-list", ListView)
        for project in proto.list_writing_projects():
            for timeline in proto.list_timelines(project["id"]):
                self._options.append((project, timeline))
                label = f"{_node_title(project)} / {timeline['fields'].get('name', '?')}"
                lv.append(ListItem(Label(label)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one("#timeline-list", ListView).index
        if idx is not None and 0 <= idx < len(self._options):
            self.dismiss(self._options[idx][1]["id"])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class ResearchResultScreen(ModalScreen):
    """Show Jeles research results for a source node."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, research: dict, *, offline: bool = False):
        super().__init__()
        self._research = research
        self._offline = offline

    def _build_md(self) -> str:
        lines = ["# Research", ""]
        if self._offline:
            lines.append("_MCP offline — research unavailable._")
            lines.append("")
        if self._research.get("error"):
            lines.append(f"**Error:** {self._research['error']}")
            lines.append("")
        r = self._research.get("research") or {}
        if r.get("query"):
            lines += [f"**Query:** {r['query']}", ""]
        if r.get("summary"):
            lines += ["## Summary", "", r["summary"], ""]
        sources = r.get("sources") or []
        if sources:
            lines += ["## Sources", ""]
            for i, src in enumerate(sources[:8], 1):
                title = src.get("title") or src.get("name") or "source"
                url = src.get("url") or ""
                lines.append(f"{i}. {title}" + (f" — {url}" if url else ""))
        return "\n".join(lines)

    def compose(self) -> ComposeResult:
        yield Vertical(
            Markdown(self._build_md(), id="research-md"),
            Button("Close", id="close-btn"),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class SuggestionReviewScreen(ModalScreen):
    """Review and accept/dismiss an SLM suggestion."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, bundle: dict):
        super().__init__()
        self._bundle = bundle
        self._suggestion = bundle["suggestion"]
        proposed = self._suggestion["fields"].get("proposed_fields", {})
        self._kind = self._suggestion["fields"].get("suggestion_kind", "")
        self._timeline_options = bundle.get("context", {}).get("timelines", [])
        self._default_timeline = proposed.get("timeline_id", "")

    def compose(self) -> ComposeResult:
        proposed = self._suggestion["fields"].get("proposed_fields", {})
        research = self._bundle.get("research") or {}
        opts = [(t["timeline_id"], t["label"]) for t in self._timeline_options]
        if not opts:
            opts = [(proposed.get("timeline_id", ""), proposed.get("timeline_label", "?"))]
        select_opts = [(label, tid) for tid, label in opts if tid]

        if self._kind == intelligence.READING_RECOMMENDATION_KIND:
            widgets = [
                Label("Reading suggestion", id="modal-title"),
                Label(f"Model: {self._suggestion['fields'].get('model', '?')}  "
                      f"confidence: {self._suggestion['fields'].get('confidence', 0)}"),
                Label("Title"),
                Input(value=proposed.get("title", ""), id="title-input"),
                Label("Author"),
                Input(value=proposed.get("author", ""), id="author-input"),
                Label("Why this belongs on to-read"),
                TextArea(proposed.get("reason", ""), id="summary-input"),
                Label("Tags"),
                Input(value=proposed.get("tags", ""), id="tags-input"),
                Horizontal(
                    Button("Add To Read", variant="primary", id="accept-btn"),
                    Button("Dismiss", id="dismiss-btn"),
                    Button("Cancel", id="cancel-btn"),
                ),
            ]
            yield Vertical(*widgets, id="modal-content")
            return

        widgets = [
            Label("Timeline promotion suggestion", id="modal-title"),
            Label(f"Model: {self._suggestion['fields'].get('model', '?')}  "
                  f"confidence: {self._suggestion['fields'].get('confidence', 0)}"),
        ]
        if research.get("summary"):
            widgets.append(Label("Jeles summary:"))
            widgets.append(Static(research["summary"][:400], id="research-preview"))
        widgets += [
            Label("Timeline"),
            Select(select_opts, id="timeline-select", value=self._default_timeline or None),
            Label("Title"),
            Input(value=proposed.get("title", ""), id="title-input"),
            Label("Summary"),
            TextArea(proposed.get("summary", ""), id="summary-input"),
            Label("Entry kind"),
            Input(value=proposed.get("entry_kind", "scene"), id="kind-input"),
            Horizontal(
                Button("Accept", variant="primary", id="accept-btn"),
                Button("Dismiss", id="dismiss-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
        ]
        yield Vertical(*widgets, id="modal-content")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        if event.button.id == "dismiss-btn":
            intelligence.dismiss_suggestion(self._suggestion["id"])
            self.dismiss({"dismissed": True})
            return
        if self._kind == intelligence.READING_RECOMMENDATION_KIND:
            self.dismiss({
                "accepted": True,
                "edits": {
                    "title": self.query_one("#title-input", Input).value.strip(),
                    "author": self.query_one("#author-input", Input).value.strip(),
                    "shelf": "to-read",
                    "reason": self.query_one("#summary-input", TextArea).text.strip(),
                    "tags": self.query_one("#tags-input", Input).value.strip(),
                },
            })
            return

        timeline_id = str(self.query_one("#timeline-select", Select).value or "")
        self.dismiss({
            "accepted": True,
            "edits": {
                "timeline_id": timeline_id,
                "title": self.query_one("#title-input", Input).value.strip(),
                "summary": self.query_one("#summary-input", TextArea).text.strip(),
                "entry_kind": self.query_one("#kind-input", Input).value.strip() or "scene",
            },
        })


class NodeDetailScreen(ModalScreen):
    """Rich node detail — fields, edges, provenance, review rendered as Markdown."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, node: dict, edges: list, *, uuid: Optional[str] = None):
        super().__init__()
        self._node = node
        self._edges = edges
        self._uuid = uuid

    def _build_md(self) -> str:
        f = self._node.get("fields", {})
        title = f.get("title") or f.get("name") or self._node["type"]
        lines = [f"# {title}", "", f"**Type:** `{self._node['type']}`", ""]
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

        if self._node["type"] == proto.TIMELINE_ENTRY:
            sources = proto.sources_for_entry(self._node["id"], uuid=self._uuid)
            if sources:
                lines += ["", "---", "", "**Derived from:**", ""]
                for src in sources:
                    lines.append(f"- [{src['type']}] {_node_title(src)}")

        if self._node["type"] in proto.PROMOTABLE_SOURCE_TYPES:
            entries = proto.entries_from_source(self._node["id"], uuid=self._uuid)
            if entries:
                lines += ["", "---", "", "**On timelines:**", ""]
                for entry in entries:
                    tl = proto.timeline_label(entry["fields"].get("timeline_id", ""))
                    lines.append(f"- {entry['fields'].get('title', '?')} ({tl})")

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
        content = f.get("content", "").strip()
        if content and self._node["type"] in ("note", proto.COMMONPLACE_ITEM):
            lines += ["", "---", "", content]
        return "\n".join(lines)

    def compose(self) -> ComposeResult:
        yield Vertical(
            Markdown(self._build_md(), id="detail-md"),
            Button("Close", id="close-btn"),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen):
    """Grouped action reference for library, writing, and intelligence."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Markdown(HELP_MD, id="help-md"),
            Button("Close", id="close-btn"),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


# ── Main App ──────────────────────────────────────────────────────────────────

class LibraryApp(App):
    TITLE = "Story Timeline"
    SUB_TITLE = "enchanted archive"

    CSS = """
    Screen {
        background: #14110e;
    }

    Header {
        background: #1c1814;
        color: #e8dcc8;
    }
    Footer {
        background: #1c1814;
        color: #a89878;
    }
    TabbedContent {
        background: #14110e;
    }
    TabPane {
        padding: 0;
    }
    Tabs {
        background: #1c1814;
        color: #a89878;
    }
    Tab {
        color: #a89878;
    }
    Tab.-active {
        color: #c9a227;
        text-style: bold;
    }
    DataTable {
        background: #1a1612;
        color: #e8dcc8;
    }
    DataTable > .datatable--cursor {
        background: #3d3428;
        color: #f5ecd8;
    }
    DataTable > .datatable--header {
        background: #252018;
        color: #c9a227;
        text-style: bold;
    }
    Tree {
        background: #1a1612;
        color: #e8dcc8;
    }
    Input {
        background: #1a1612;
        border: solid #3d3428;
        color: #e8dcc8;
    }
    Input:focus {
        border: solid #c9a227;
    }

    /* Modals */
    CreateNodeScreen, NodePickerScreen, NodeDetailScreen,
    ImportScreen, ExportListScreen, RelationScreen, CreateProjectScreen,
    CreateTimelineScreen, TimelinePickerScreen,
    SuggestionReviewScreen, ResearchResultScreen, HelpScreen { align: center middle; }

    #modal-content {
        background: #1a1612;
        border: solid #c9a227;
        padding: 1 2;
        width: 80;
        height: auto;
        max-height: 90vh;
    }
    NodeDetailScreen #modal-content { width: 90; }
    #modal-title { text-style: bold; color: #c9a227; margin-bottom: 1; }
    #detail-md { height: 30; border: solid #3d3428; padding: 0 1; }
    #picker-list { height: 14; border: solid #3d3428; }
    #research-md { height: 20; border: solid #3d3428; padding: 0 1; }
    #research-preview { height: 4; color: #a89878; }
    #summary-input { height: 8; }
    #help-md { height: 24; border: solid #3d3428; padding: 0 1; }

    /* Chrome */
    #desk-chrome { height: auto; background: #1c1814; border-bottom: solid #3d3428; }
    #breadcrumb {
        height: 1;
        padding: 0 1;
        color: #c9a227;
        text-style: bold;
        background: #252018;
    }
    #willow-pulse {
        height: 1;
        padding: 0 1;
        color: #a89878;
        background: #1c1814;
    }

    /* Layout */
    #home-dashboard { height: 1fr; padding: 1 2; color: #e8dcc8; }
    #selected-context-books, #selected-context-notes, #selected-context-all {
        height: 3;
        color: #a89878;
        padding: 0 1;
        border-top: solid #3d3428;
        background: #1a1612;
    }
    #writing-context {
        height: auto;
        max-height: 6;
        color: #a89878;
        padding: 0 1;
        border-top: solid #3d3428;
        background: #1a1612;
    }
    #river-banner {
        height: 3;
        padding: 0 1;
        color: #e8b86d;
        text-style: italic;
        background: #252018;
        border-bottom: solid #3d3428;
    }
    #inbox-banner {
        height: 2;
        padding: 0 1;
        color: #e8b86d;
        background: #252018;
        border-bottom: solid #3d3428;
    }
    #constellation-hint {
        height: 2;
        padding: 0 1;
        color: #a89878;
        background: #1a1612;
        border-bottom: solid #3d3428;
    }
    #intelligence-table { height: 1fr; }
    #intelligence-hint { height: 1; color: #a89878; padding: 0 1; }
    #books-layout { height: 1fr; }
    #sidebar { width: 26; border-right: solid #3d3428; padding: 0 1; background: #1a1612; }
    #sidebar-heading { text-style: bold; color: #c9a227; margin-bottom: 1; }
    #content-panel { width: 1fr; }
    #search-input { width: 1fr; }
    #node-table { height: 1fr; }
    #status { height: 2; color: #a89878; padding: 0 1; }
    #author-table, #notes-table, #all-table { height: 1fr; }
    #writing-layout { height: 1fr; }
    #project-table, #timeline-table { height: 10; }
    #entry-table { height: 1fr; }
    .writing-heading { text-style: bold; color: #c9a227; margin: 1 0 0 0; }
    .tab-empty-hint {
        height: 2;
        padding: 0 1;
        color: #a89878;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("a", "add_node", "Add"),
        Binding("e", "edit_node", "Edit"),
        Binding("d", "delete_node", "Delete"),
        Binding("l", "link_node", "Link"),
        Binding("v", "view_node", "View"),
        Binding("p", "promote_node", "Promote"),
        Binding("j", "research_node", "Research"),
        Binding("s", "suggest_node", "Suggest"),
        Binding("i", "import_csv", "Import"),
        Binding("o", "export_list", "Export"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("h", "help", "Help"),
        Binding("question_mark", "help", "Help"),
        Binding("enter", "accept_suggestion", "Accept", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, uuid: Optional[str] = None):
        super().__init__()
        self._uuid = uuid
        self._book_ids: list[str] = []
        self._author_ids: list[str] = []
        self._note_ids: list[str] = []
        self._all_ids: list[str] = []
        self._project_ids: list[str] = []
        self._timeline_ids: list[str] = []
        self._entry_ids: list[str] = []
        self._selected_project_id: Optional[str] = None
        self._selected_timeline_id: Optional[str] = None
        self._shelf_filter: Optional[str] = None
        self._tag_filter: Optional[str] = None
        self._search: Optional[str] = None
        self._link_target: str = ""
        self._stats = {"nodes_created": 0, "edges_created": 0}
        self._intelligence_rows: list[dict] = []
        self._last_promotable: Optional[dict] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="desk-chrome"):
            yield Static("› Desk", id="breadcrumb")
            yield Static("", id="willow-pulse", markup=True)
        with TabbedContent(id="tabs"):
            with TabPane("Desk", id="tab-home"):
                yield Static("", id="home-dashboard", markup=True)
            with TabPane("Shelves", id="tab-books"):
                yield Horizontal(
                    Vertical(
                        Label("◈ SHELVES", id="sidebar-heading"),
                        Tree("◎ All volumes", id="shelf-tree"),
                        id="sidebar",
                    ),
                    Vertical(
                        Input(placeholder="hunt across the shelves…", id="search-input"),
                        DataTable(id="node-table", cursor_type="row", zebra_stripes=True),
                        Static("", id="status"),
                        Static(
                            "Pick a volume · j ask Jeles · s suggest to-read · p promote to canon · v open",
                            id="selected-context-books",
                        ),
                        id="content-panel",
                    ),
                    id="books-layout",
                )
            with TabPane("Authors", id="tab-authors"):
                yield Vertical(
                    Static("", id="authors-empty", classes="tab-empty-hint"),
                    DataTable(id="author-table", cursor_type="row", zebra_stripes=True),
                )
            with TabPane("Commonplace", id="tab-notes"):
                yield Vertical(
                    DataTable(id="notes-table", cursor_type="row", zebra_stripes=True),
                    Static(
                        "Pick a scrap · j open research packet · s suggest to-read · p promote to canon",
                        id="selected-context-notes",
                    ),
                )
            with TabPane("Timelines", id="tab-writing"):
                yield Vertical(
                    Static(
                        "〜 the river — projects upstream, lanes midstream, beats downstream",
                        id="river-banner",
                    ),
                    Label("◆ Projects", classes="writing-heading"),
                    DataTable(id="project-table", cursor_type="row", zebra_stripes=True),
                    Label("◇ Lanes", classes="writing-heading"),
                    DataTable(id="timeline-table", cursor_type="row", zebra_stripes=True),
                    Label("▸ Beats", classes="writing-heading"),
                    DataTable(id="entry-table", cursor_type="row", zebra_stripes=True),
                    Static(
                        "Follow a lane to see loose threads bound for it.",
                        id="writing-context",
                    ),
                    id="writing-layout",
                )
            with TabPane("Jeles Inbox", id="tab-intelligence"):
                yield Vertical(
                    Static(
                        "⌁ signals from Jeles and the local SLM — nothing becomes canon until you accept",
                        id="inbox-banner",
                    ),
                    Static(
                        "v review · Enter accept / add to shelf · d dismiss",
                        id="intelligence-hint",
                    ),
                    DataTable(id="intelligence-table", cursor_type="row", zebra_stripes=True),
                )
            with TabPane("Constellation", id="tab-all"):
                yield Vertical(
                    Static(
                        "✦ every star in your graph — books, scraps, themes, people, places",
                        id="constellation-hint",
                    ),
                    DataTable(id="all-table", cursor_type="row", zebra_stripes=True),
                    Static(
                        "Pick a star · j research · s suggest to-read · p promote · v inspect",
                        id="selected-context-all",
                    ),
                )
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild_chrome()
        self._rebuild_home()
        self._rebuild_shelf_tree()
        self._rebuild_books_table()
        self._rebuild_author_table()
        self._rebuild_notes_table()
        self._rebuild_all_table()
        self._rebuild_writing_tables()
        self._rebuild_intelligence_table()

    # ── Dashboard & intelligence views ─────────────────────────────────────────

    def _counts(self) -> dict[str, int]:
        return suggestions.dashboard_counts()

    def _format_home(self) -> str:
        c = self._counts()
        setup = proto.writing_setup_status()
        return _format_home_map(c, ready=setup["ready"])

    def _rebuild_chrome(self) -> None:
        try:
            tab = self._active_tab()
            crumb = _TAB_CRUMB.get(tab, "Desk")
            self.query_one("#breadcrumb", Static).update(f"› {crumb}")
            self.query_one("#willow-pulse", Static).update(_willow_pulse())
        except Exception:
            pass

    def _rebuild_home(self) -> None:
        try:
            self.query_one("#home-dashboard", Static).update(self._format_home())
        except Exception:
            pass

    def _selected_context(self, node: Optional[dict]) -> str:
        if not node or node["type"] not in proto.PROMOTABLE_SOURCE_TYPES:
            return (
                "Pick a volume, scrap, or library project · j ask Jeles · "
                "s suggest to-read · p promote to canon · v inspect"
            )
        entries = proto.entries_from_source(node["id"], uuid=self._uuid)
        counts = suggestions.counts_for_source(node["id"])
        glyph = _type_glyph(node["type"])
        return (
            f"{glyph} {_node_title(node)} · in canon on {len(entries)} lane(s) · "
            f"{counts['research']} research packet(s) · "
            f"{counts['pending_suggestions']} loose thread(s) · "
            f"j · s · p · v"
        )

    def _rebuild_selected_context(self, strip_id: str, node: Optional[dict] = None) -> None:
        try:
            self.query_one(strip_id, Static).update(self._selected_context(node))
        except Exception:
            pass

    def _rebuild_intelligence_table(self) -> None:
        try:
            table = self.query_one("#intelligence-table", DataTable)
        except Exception:
            return
        table.clear(columns=True)
        table.add_columns("Signal", "From", "Whisper", "Fate", "Voice")
        self._intelligence_rows = []

        for suggestion in suggestions.list_suggestions(status=suggestions.STATUS_PENDING):
            src = db.get_node(suggestion["fields"].get("source_id", ""))
            src_title = _node_title(src) if src else "?"
            proposed = suggestion["fields"].get("proposed_fields", {})
            kind = suggestion["fields"].get("suggestion_kind", "")
            is_reading = kind == intelligence.READING_RECOMMENDATION_KIND
            target = (
                f"{proposed.get('title', '—')} → to-read"
                if is_reading
                else (proposed.get("timeline_label") or proposed.get("title", "—"))
            )
            self._intelligence_rows.append({
                "kind": "suggestion",
                "id": suggestion["id"],
                "node": suggestion,
            })
            table.add_row(
                "◎ shelf" if is_reading else "▸ canon",
                src_title[:30],
                str(target)[:40],
                "loose",
                str(suggestion["fields"].get("model", "—"))[:16],
            )

        for packet in suggestions.list_research(limit=20):
            src = db.get_node(packet["fields"].get("source_id", ""))
            src_title = _node_title(src) if src else "?"
            summary = packet["fields"].get("summary", "")[:40]
            self._intelligence_rows.append({
                "kind": "research",
                "id": packet["id"],
                "node": packet,
            })
            table.add_row(
                "⌁ packet",
                src_title[:30],
                summary or packet["fields"].get("query", "")[:40],
                "filed",
                str(packet["fields"].get("provider", "—"))[:16],
            )

        if not self._intelligence_rows:
            table.add_row("—", "—", _EMPTY_VOICES["intelligence"], "—", "—")

    def _rebuild_writing_context(self) -> None:
        try:
            strip = self.query_one("#writing-context", Static)
        except Exception:
            return
        if not self._selected_timeline_id:
            strip.update(
                "Choose a lane · loose threads bound for it appear here · "
                "p promotes scraps into beats · s suggests volumes for the shelf"
            )
            return
        tl_label = proto.timeline_label(self._selected_timeline_id)
        pending = suggestions.pending_for_timeline(self._selected_timeline_id)
        entries = proto.list_timeline_entries(self._selected_timeline_id)
        lines = [
            f"Lane: {tl_label} · {len(entries)} beat(s) · "
            f"{len(pending)} loose thread(s) drifting here",
        ]
        for suggestion in pending[:4]:
            src = db.get_node(suggestion["fields"].get("source_id", ""))
            src_title = _node_title(src) if src else "?"
            prop = suggestion["fields"].get("proposed_fields", {})
            lines.append(f"  → {src_title}: {prop.get('title', '?')[:42]}")
        if pending:
            lines.append("Jeles Inbox · Enter weave in · v read whisper · d cut thread")
        strip.update("\n".join(lines))

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        tab_id = event.tab.id or ""
        self._rebuild_chrome()
        if tab_id == "tab-home":
            self._rebuild_home()
        elif tab_id == "tab-intelligence":
            self._rebuild_intelligence_table()

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
        root.add_leaf(f"◎ All volumes  ({len(books)})", data={"filter": "all"})

        if shelf_counts:
            shelves = root.add("◈ By shelf", data=None)
            for shelf in ("read", "currently-reading", "to-read", "dnf"):
                count = shelf_counts.get(shelf, 0)
                if count:
                    shelves.add_leaf(
                        f"{_shelf_glyph(shelf)} {_shelf_label(shelf)}  ({count})",
                        data={"filter": "shelf", "value": shelf},
                    )
            shelves.expand()

        if tag_counts:
            tags_node = root.add("✦ Tags", data=None)
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
        table.add_columns("", "Title", "Author", "Stars", "Shelf", "Read")

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
        if not nodes:
            table.add_row("◎", "—", "—", "—", "—", _EMPTY_VOICES["books"][:40])
        for n in nodes:
            f = n["fields"]
            shelf = f.get("shelf", "")
            table.add_row(
                _shelf_glyph(shelf),
                f.get("title", "—")[:48],
                f.get("author", "—")[:24],
                _stars(f.get("rating", 0)),
                _shelf_label(shelf),
                (f.get("date_read") or "")[:10],
            )

        parts = [f"{len(nodes)} volume(s) on the shelf"]
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
        table.add_columns("", "Name", "Marginalia")
        authors = db.get_nodes(type_="author")
        self._author_ids = [a["id"] for a in authors]
        try:
            hint = self.query_one("#authors-empty", Static)
            hint.update("" if authors else _EMPTY_VOICES["authors"])
        except Exception:
            pass
        if not authors:
            table.add_row("✒", "—", _EMPTY_VOICES["authors"][:58])
        for a in authors:
            f = a["fields"]
            table.add_row("✒", f.get("name", "—"), f.get("notes", "")[:58])

    def _rebuild_notes_table(self) -> None:
        table = self.query_one("#notes-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", "Scrap", "Preview")
        notes = db.get_nodes(type_="note")
        self._note_ids = [n["id"] for n in notes]
        if not notes:
            table.add_row("✎", "—", _EMPTY_VOICES["notes"][:68])
        for n in notes:
            f = n["fields"]
            title = f.get("title") or f.get("name") or "—"
            preview = f.get("content") or f.get("summary") or ""
            table.add_row("✎", title[:46], preview[:68])

    def _rebuild_all_table(self) -> None:
        table = self.query_one("#all-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", "Kind", "Star", "Tail")
        nodes = db.get_nodes()
        self._all_ids = [n["id"] for n in nodes]
        if not nodes:
            table.add_row("✦", "—", _EMPTY_VOICES["constellation"][:50], "—")
        for n in nodes:
            table.add_row(
                _type_glyph(n["type"]),
                n["type"],
                _node_title(n)[:52],
                n["id"][:14] + "…",
            )

    # ── Writing tab ───────────────────────────────────────────────────────────

    def _rebuild_writing_tables(self) -> None:
        self._rebuild_project_table()
        self._rebuild_timeline_table()
        self._rebuild_entry_table()
        self._rebuild_writing_context()

    def _rebuild_project_table(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", "Project", "Mood")
        projects = proto.list_writing_projects()
        self._project_ids = [p["id"] for p in projects]
        if self._selected_project_id not in self._project_ids:
            self._selected_project_id = self._project_ids[0] if self._project_ids else None
        if not projects:
            table.add_row("◆", "—", _EMPTY_VOICES["writing"][:40])
        for p in projects:
            f = p["fields"]
            table.add_row("◆", f.get("title", "—")[:46], f.get("status", "—")[:18])

    def _rebuild_timeline_table(self) -> None:
        table = self.query_one("#timeline-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", "Lane", "Current")
        timelines = (
            proto.list_timelines(self._selected_project_id)
            if self._selected_project_id else []
        )
        self._timeline_ids = [t["id"] for t in timelines]
        if self._selected_timeline_id not in self._timeline_ids:
            self._selected_timeline_id = self._timeline_ids[0] if self._timeline_ids else None
        if not timelines and self._selected_project_id:
            table.add_row("◇", "—", "Add a lane with a")
        for t in timelines:
            f = t["fields"]
            table.add_row("◇", f.get("name", "—")[:46], f.get("timeline_kind", "—")[:18])

    def _rebuild_entry_table(self) -> None:
        table = self.query_one("#entry-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", "#", "Beat", "Shape", "When")
        entries = (
            proto.list_timeline_entries(self._selected_timeline_id)
            if self._selected_timeline_id else []
        )
        self._entry_ids = [e["id"] for e in entries]
        if not entries and self._selected_timeline_id:
            table.add_row("▸", "—", "—", "—", _EMPTY_VOICES["entries"][:30])
        for e in entries:
            f = e["fields"]
            table.add_row(
                "▸",
                str(f.get("order_index", 0)),
                f.get("title", "—")[:44],
                f.get("entry_kind", "—")[:14],
                (f.get("world_date") or "")[:14],
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        table_id = event.data_table.id
        row = event.cursor_row
        if table_id == "project-table":
            if 0 <= row < len(self._project_ids):
                self._selected_project_id = self._project_ids[row]
                self._selected_timeline_id = None
                self._rebuild_timeline_table()
                self._rebuild_entry_table()
                self._rebuild_writing_context()
        elif table_id == "timeline-table":
            if 0 <= row < len(self._timeline_ids):
                self._selected_timeline_id = self._timeline_ids[row]
                self._rebuild_entry_table()
                self._rebuild_writing_context()
        elif table_id == "node-table":
            node = self._selected_from_table("#node-table", self._book_ids)
            self._remember_promotable(node)
            self._rebuild_selected_context("#selected-context-books", node)
        elif table_id == "notes-table":
            node = self._selected_from_table("#notes-table", self._note_ids)
            self._remember_promotable(node)
            self._rebuild_selected_context("#selected-context-notes", node)
        elif table_id == "all-table":
            node = self._selected_from_table("#all-table", self._all_ids)
            if node and node["type"] in proto.PROMOTABLE_SOURCE_TYPES:
                self._remember_promotable(node)
                self._rebuild_selected_context("#selected-context-all", node)
            else:
                self._rebuild_selected_context("#selected-context-all", None)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._rebuild_chrome()
        self._rebuild_home()
        self._rebuild_shelf_tree()
        self._rebuild_books_table()
        self._rebuild_author_table()
        self._rebuild_notes_table()
        self._rebuild_all_table()
        self._rebuild_writing_tables()
        self._rebuild_intelligence_table()

    def _remember_promotable(self, node: Optional[dict]) -> None:
        if node and node["type"] in proto.PROMOTABLE_SOURCE_TYPES:
            self._last_promotable = node

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
        if tab == "tab-writing":
            return self._selected_from_table("#entry-table", self._entry_ids)
        return None

    def _promotable_node(self) -> Optional[dict]:
        tab = self._active_tab()
        node: Optional[dict] = None
        if tab == "tab-books":
            node = self._selected_from_table("#node-table", self._book_ids)
        elif tab == "tab-notes":
            node = self._selected_from_table("#notes-table", self._note_ids)
        elif tab == "tab-all":
            node = self._selected_from_table("#all-table", self._all_ids)
        elif tab == "tab-authors":
            node = self._selected_from_table("#author-table", self._author_ids)
        elif tab == "tab-intelligence":
            item = self._selected_intelligence_item()
            if item:
                source_id = item["node"]["fields"].get("source_id")
                if source_id:
                    node = db.get_node(source_id)

        if node and node["type"] in proto.PROMOTABLE_SOURCE_TYPES:
            return node
        return self._last_promotable

    def _promotable_label(self) -> str:
        node = self._promotable_node()
        if node:
            return f"{_node_title(node)} ({node['type']})"
        return "a book or note"

    def _ensure_writing_ready(self, on_ready) -> None:
        """Create writing project + timeline inline when promotion/suggest needs them."""
        status = proto.writing_setup_status()
        if status["ready"]:
            on_ready()
            return

        if status["needs_project"]:
            def on_project(result: Optional[dict]) -> None:
                if not result:
                    self.notify("Writing project required.", severity="warning")
                    return
                project = proto.create_writing_project(
                    result["title"], summary=result.get("summary", "")
                )
                self._selected_project_id = project["id"]
                self._stats["nodes_created"] += 1
                timeline = proto.create_timeline(
                    project["id"], "World", timeline_kind="world"
                )
                if self._uuid:
                    proto.wire_timeline_to_project(
                        timeline["id"], project["id"], uuid=self._uuid
                    )
                    import soil_protocol
                    soil_protocol.mirror_protocol_record(timeline, uuid=self._uuid)
                self._selected_timeline_id = timeline["id"]
                self._stats["nodes_created"] += 1
                self._refresh_all()
                self.notify(f"Created writing project and timeline World.")
                on_ready()

            self.notify("Set up a writing project — suggestions attach to its timelines.")
            self.push_screen(CreateProjectScreen(), on_project)
            return

        projects = proto.list_writing_projects()
        project = (
            proto.get_writing_project(self._selected_project_id)
            if self._selected_project_id else None
        ) or projects[0]
        project_title = _node_title(project)

        def on_timeline(result: Optional[dict]) -> None:
            if not result:
                self.notify("Timeline required.", severity="warning")
                return
            timeline = proto.create_timeline(
                result["project_id"],
                result["name"],
                timeline_kind=result.get("kind", "world"),
            )
            if self._uuid:
                proto.wire_timeline_to_project(
                    timeline["id"], result["project_id"], uuid=self._uuid
                )
                import soil_protocol
                soil_protocol.mirror_protocol_record(timeline, uuid=self._uuid)
            self._selected_timeline_id = timeline["id"]
            self._stats["nodes_created"] += 1
            self._refresh_all()
            self.notify(f"Timeline: {result['name']}")
            on_ready()

        self.notify("Add a timeline under your writing project.")
        self.push_screen(
            CreateTimelineScreen(project["id"], project_title), on_timeline
        )

    def _active_tab(self) -> str:
        try:
            return str(self.query_one("#tabs", TabbedContent).active)
        except Exception:
            return "tab-books"

    def _selected_intelligence_item(self) -> Optional[dict]:
        if self._active_tab() != "tab-intelligence":
            return None
        table = self.query_one("#intelligence-table", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._intelligence_rows):
            return None
        return self._intelligence_rows[row]

    def _switch_tab(self, tab_id: str) -> None:
        try:
            self.query_one("#tabs", TabbedContent).active = tab_id
        except Exception:
            pass

    def action_go_home(self) -> None:
        self._switch_tab("tab-home")
        self._rebuild_home()

    def action_go_intelligence(self) -> None:
        self._switch_tab("tab-intelligence")
        self._rebuild_intelligence_table()

    def _default_type_for_tab(self) -> str:
        return {"tab-authors": "author", "tab-notes": "note"}.get(self._active_tab(), "book")

    def _finish_suggestion_accept(self, bundle: dict, result: dict) -> None:
        try:
            out = intelligence.accept_suggestion(
                bundle["suggestion"]["id"],
                uuid=self._uuid,
                edits=result.get("edits"),
            )
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if "book" in out:
            self._stats["nodes_created"] += 1
            self._refresh_all()
            book = out["book"]
            self.notify(f"Added to-read → {book['fields'].get('title', '?')}")
            return
        promo = out["promotion"]
        self._stats["nodes_created"] += 1
        self._stats["edges_created"] += sum(
            1 for v in promo["edges"].values() if v
        )
        tl_id = result.get("edits", {}).get("timeline_id")
        if tl_id:
            self._selected_timeline_id = tl_id
        self._refresh_all()
        entry = promo["entry"]
        tl_name = promo["provenance"].get("timeline_name", "")
        self.notify(f"Accepted → {entry['fields'].get('title', '?')} on {tl_name}")

    def _open_suggestion_review(self, suggestion_node: dict) -> None:
        try:
            bundle = intelligence.bundle_for_suggestion(suggestion_node["id"])
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return

        def on_review(result: Optional[dict]) -> None:
            if not result or not result.get("accepted"):
                if result and result.get("dismissed"):
                    self._refresh_all()
                    self.notify("Suggestion dismissed.")
                return
            self._finish_suggestion_accept(bundle, result)

        self.push_screen(SuggestionReviewScreen(bundle), on_review)

    # ── Input handler ─────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._search = event.value.strip() or None
            self._shelf_filter = None
            self._tag_filter = None
            self._rebuild_books_table()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_add_node(self) -> None:
        if self._active_tab() == "tab-writing":
            self._add_writing_item()
            return

        def on_dismiss(result):
            if result:
                type_ = result["type"]
                if type_ == proto.WRITING_PROJECT:
                    proto.create_writing_project(
                        result["fields"].get("title", ""),
                        summary=result["fields"].get("summary", ""),
                        status=result["fields"].get("status", "planning"),
                    )
                else:
                    db.add_node(type_=type_, fields=result["fields"])
                self._stats["nodes_created"] += 1
                self._refresh_all()
                self.notify(f"Added {type_}.")
        self.push_screen(CreateNodeScreen(default_type=self._default_type_for_tab()), on_dismiss)

    def _add_writing_item(self) -> None:
        if not self._selected_project_id:
            def on_project(result):
                if not result:
                    return
                project = proto.create_writing_project(
                    result["title"], summary=result.get("summary", "")
                )
                self._selected_project_id = project["id"]
                self._stats["nodes_created"] += 1
                self._refresh_all()
                self.notify(f"Project: {result['title']}")
            self.push_screen(CreateProjectScreen(), on_project)
            return

        if not self._selected_timeline_id:
            project = proto.get_writing_project(self._selected_project_id)
            title = _node_title(project) if project else "?"

            def on_timeline(result):
                if not result:
                    return
                timeline = proto.create_timeline(
                    result["project_id"],
                    result["name"],
                    timeline_kind=result.get("kind", "world"),
                )
                if self._uuid:
                    proto.wire_timeline_to_project(
                        timeline["id"], result["project_id"], uuid=self._uuid
                    )
                    import soil_protocol
                    soil_protocol.mirror_protocol_record(timeline, uuid=self._uuid)
                self._selected_timeline_id = timeline["id"]
                self._stats["nodes_created"] += 1
                self._refresh_all()
                self.notify(f"Timeline: {result['name']}")
            self.push_screen(
                CreateTimelineScreen(self._selected_project_id, title), on_timeline
            )
            return

        self.notify("Select a note or book and press p to promote into this timeline.")

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
        if self._active_tab() == "tab-intelligence":
            self.action_dismiss_selected_suggestion()
            return
        node = self._selected_node()
        if node and db.delete_node(node["id"]):
            self._refresh_all()
            self.notify("Deleted.")

    def action_dismiss_selected_suggestion(self) -> None:
        item = self._selected_intelligence_item()
        if not item or item["kind"] != "suggestion":
            self.notify("Select a pending suggestion to dismiss.", severity="warning")
            return
        suggestion = item["node"]
        if suggestion["fields"].get("status") != suggestions.STATUS_PENDING:
            self.notify("Only pending suggestions can be dismissed.", severity="warning")
            return
        if intelligence.dismiss_suggestion(suggestion["id"]):
            self._refresh_all()
            self.notify("Suggestion dismissed.")

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
        if self._active_tab() == "tab-intelligence":
            self.action_review_suggestion()
            return
        node = self._selected_node()
        if not node:
            return
        if node["type"] == suggestions.RESEARCH_PACKET:
            view = intelligence.research_view_for_packet(node)
            self.push_screen(
                ResearchResultScreen(view, offline=not view.get("ok", False)),
            )
            return
        if node["type"] == suggestions.SLM_SUGGESTION:
            try:
                self._open_suggestion_review(node)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
            return
        edges = willow_edges.edges_for(node["id"], uuid=self._uuid)
        self.push_screen(NodeDetailScreen(node=node, edges=edges, uuid=self._uuid))

    def action_review_suggestion(self) -> None:
        item = self._selected_intelligence_item()
        if not item:
            self.notify("Select a suggestion or research row.", severity="warning")
            return
        if item["kind"] == "suggestion":
            self._open_suggestion_review(item["node"])
            return
        packet = item["node"]
        view = intelligence.research_view_for_packet(packet)
        self.push_screen(
            ResearchResultScreen(view, offline=not view.get("ok", False)),
        )

    def action_accept_suggestion(self) -> None:
        if self._active_tab() != "tab-intelligence":
            return
        item = self._selected_intelligence_item()
        if not item or item["kind"] != "suggestion":
            return
        suggestion = item["node"]
        if suggestion["fields"].get("status") != suggestions.STATUS_PENDING:
            return
        try:
            bundle = intelligence.bundle_for_suggestion(suggestion["id"])
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        proposed = dict(suggestion["fields"].get("proposed_fields") or {})
        self._finish_suggestion_accept(bundle, {"edits": proposed})

    def action_promote_node(self) -> None:
        node = self._promotable_node()
        if not node:
            self.notify(
                "Select a library item in Books or Notes (or create a note first).",
                severity="warning",
            )
            return

        def on_ready() -> None:
            def on_timeline(timeline_id: Optional[str]) -> None:
                if not timeline_id:
                    return
                try:
                    result = proto.promote_to_timeline(
                        node["id"],
                        timeline_id,
                        uuid=self._uuid,
                        mirror=bool(self._uuid),
                    )
                except ValueError as exc:
                    self.notify(str(exc), severity="error")
                    return
                self._stats["nodes_created"] += 1
                self._stats["edges_created"] += sum(
                    1 for v in result["edges"].values() if v
                )
                self._selected_timeline_id = timeline_id
                self._refresh_all()
                entry = result["entry"]
                tl_name = result["provenance"].get("timeline_name", "")
                self.notify(f"Promoted → {entry['fields'].get('title', '?')} on {tl_name}")

            self.push_screen(TimelinePickerScreen(), on_timeline)

        self._ensure_writing_ready(on_ready)

    def action_research_node(self) -> None:
        node = self._promotable_node()
        if not node:
            self.notify(
                f"Select {self._promotable_label()} to research.",
                severity="warning",
            )
            return
        try:
            result = intelligence.run_jeles_research(node)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        offline = not result.get("ok", False)
        self.push_screen(
            ResearchResultScreen(result, offline=offline),
        )
        if result.get("ok"):
            self._refresh_all()
            self.notify("Research saved.")
        else:
            self.notify(result.get("error", "Research unavailable"), severity="warning")

    def action_suggest_node(self) -> None:
        node = self._promotable_node()
        if not node:
            self.notify(
                f"Select {self._promotable_label()} to suggest to-read works for.",
                severity="warning",
            )
            return

        try:
            bundle = intelligence.suggest_reading_recommendations(node)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return

        suggestion_count = len(bundle.get("suggestions") or [])
        if not suggestion_count:
            self.notify("No reading suggestions were produced.", severity="warning")
            return
        self._refresh_all()
        msg = "offline heuristic" if bundle.get("offline") else "SLM reading suggestions ready"
        self.notify(f"{msg}: {suggestion_count}")
        first = bundle.get("suggestion")
        if first:
            self._open_suggestion_review(first)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_export_list(self) -> None:
        source = self._promotable_node()
        source_id = source["id"] if source else ""
        source_label = _node_title(source) if source else ""

        def on_export(result: Optional[dict]) -> None:
            if not result:
                return
            scope = result.get("scope", "to-read")
            if scope == "selected-source" and not source_id:
                self.notify("Select a source with pending recommendations first.", severity="warning")
                return
            books = export_lists.books_for_scope(scope, source_id=source_id)
            out = export_lists.export_bundle(books, label=result.get("label") or scope)
            self.notify(
                f"Exported {out['count']} book(s): {Path(out['markdown']).name} and {Path(out['csv']).name}"
            )

        self.push_screen(
            ExportListScreen(has_source=bool(source), source_label=source_label),
            on_export,
        )

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
        self.notify("Desk rearranged.")

    def action_quit(self) -> None:
        if self._uuid:
            safe_integration.write_session_composite(
                stats={**self._stats, "types_used": []}, uuid=self._uuid
            )
        self.exit()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    uuid = safe_integration.get_user_uuid()
    if not uuid:
        sys.stderr.write(
            "Warning: ~/.willow/user_identity.json not found — Willow edges disabled.\n\n"
        )
    boot = boot_sequence(uuid=uuid)
    if boot["migrated"]:
        print(f"Migrated {boot['migrated']} v1 event(s).")
    LibraryApp(uuid=uuid).run()


if __name__ == "__main__":
    main()
