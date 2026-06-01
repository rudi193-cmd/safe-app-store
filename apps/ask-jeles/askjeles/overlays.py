"""Modal overlays — dismiss returns to the desk, not a clean search."""

from __future__ import annotations

import json
import time
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, ListItem, ListView, Static
from textual import work

from askjeles import mcp_adapters as _mcp_adapters
from askjeles import mcp_generic as _mcp_generic
from askjeles import mcp_registry as _mcp_registry
from askjeles import trivia as _trivia


class TriviaModal(ModalScreen[dict[str, Any] | None]):
    """Quiz overlay from current search results. Dismiss restores underlying search UI."""

    DEFAULT_CSS = """
    TriviaModal {
        align: center middle;
    }
    #trivia-box {
        width: 72;
        max-width: 90;
        height: auto;
        max-height: 22;
        border: solid #9a7b3c;
        background: #1a1510;
        padding: 1 2;
    }
    #trivia-progress {
        height: 1;
        color: #9a7b3c;
    }
    #trivia-category {
        height: 1;
        color: #c4a456;
    }
    #trivia-question {
        height: auto;
        max-height: 6;
        margin: 1 0;
    }
    #trivia-options {
        height: auto;
        margin: 1 0;
    }
    #trivia-feedback {
        height: auto;
        max-height: 4;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("a", "answer_a", "A", show=False),
        Binding("b", "answer_b", "B", show=False),
        Binding("c", "answer_c", "C", show=False),
        Binding("d", "answer_d", "D", show=False),
    ]

    def __init__(
        self,
        query: str,
        hits: list[dict[str, Any]],
        synthesis: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._query = query
        self._hits = hits
        self._synthesis = synthesis
        self._bank: list[dict[str, Any]] = []
        self._idx = 0
        self._score = 0
        self._awaiting_next = False
        self._answered_count = 0
        self._completed = False
        self._started_at = 0.0

    def compose(self) -> ComposeResult:
        with Container(id="trivia-box"):
            yield Label("Jeles // Trivia", id="trivia-title")
            yield Static("Preparing quiz from your search…", id="trivia-progress")
            yield Label("", id="trivia-category")
            yield Static("", id="trivia-question", markup=True)
            yield Vertical(id="trivia-options")
            yield Static("", id="trivia-feedback", markup=True)
            yield Static("[dim]A–D answer · Esc or q close[/]", id="trivia-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._started_at = time.time()
        self._load_bank()

    @work(exclusive=True, thread=True)
    def _load_bank(self) -> None:
        bank = _trivia.generate_from_search(
            self._query, self._hits, synthesis=self._synthesis
        )
        if not bank:
            bank = _trivia.TRIVIA_BANK[:3]
        self.app.call_from_thread(self._start_quiz, bank)

    def _start_quiz(self, bank: list[dict[str, Any]]) -> None:
        self._bank = bank
        self._idx = 0
        self._score = 0
        self._show_question()

    def _show_question(self) -> None:
        if self._idx >= len(self._bank):
            self._show_final()
            return
        q = self._bank[self._idx]
        total = len(self._bank)
        self.query_one("#trivia-progress", Static).update(
            f"Question {self._idx + 1}/{total} · Score {self._score}/{total * 10}"
        )
        self.query_one("#trivia-category", Label).update(q.get("category", ""))
        self.query_one("#trivia-question", Static).update(q.get("question", ""))

        opts = self.query_one("#trivia-options", Vertical)
        opts.remove_children()
        for i, opt in enumerate((q.get("options") or [])[:4]):
            opts.mount(Label(f"[bold cyan]{_trivia.LABELS[i]}[/] {opt}"))

        self.query_one("#trivia-feedback", Static).update("")
        self._awaiting_next = False

    def _show_final(self) -> None:
        self._completed = True
        total = len(self._bank) or 1
        pct = (self._score / (total * 10)) * 100 if total else 0
        status = "High Sovereignty" if pct >= 80 else "High Entropy"
        self.query_one("#trivia-progress", Static).update("Quiz complete")
        self.query_one("#trivia-category", Label).update("FROM YOUR SEARCH")
        self.query_one("#trivia-question", Static).update(
            f"Final score: {self._score}/{total * 10} ({pct:.0f}%)\n{status}"
        )
        self.query_one("#trivia-options", Vertical).remove_children()
        self.query_one("#trivia-feedback", Static).update(
            "[dim]Press Esc or q to return to your search desk.[/]"
        )

    def _grade(self, choice: str) -> None:
        if self._awaiting_next or self._idx >= len(self._bank):
            return
        q = self._bank[self._idx]
        correct = choice == q.get("answer")
        if correct:
            self._score += 10
            fb = f"[green]Correct.[/] {q.get('explanation', '')}"
        else:
            fb = (
                f"[red]Expected [{q.get('answer')}].[/] "
                f"{q.get('explanation', '')}"
            )
        self.query_one("#trivia-feedback", Static).update(fb)
        self._answered_count += 1
        self._awaiting_next = True
        self.set_timer(1.2, self._next_question, name="trivia-advance")

    def _next_question(self) -> None:
        self._idx += 1
        self._show_question()

    def _result_payload(self) -> dict[str, Any]:
        duration_s = round(time.time() - self._started_at, 1) if self._started_at else 0.0
        total = len(self._bank)
        return {
            "score": self._score,
            "total": total,
            "answered": self._answered_count,
            "completed": self._completed,
            "query": self._query,
            "duration_s": duration_s,
        }

    def action_dismiss_modal(self) -> None:
        self.dismiss(self._result_payload())

    def action_answer_a(self) -> None:
        self._grade("A")

    def action_answer_b(self) -> None:
        self._grade("B")

    def action_answer_c(self) -> None:
        self._grade("C")

    def action_answer_d(self) -> None:
        self._grade("D")


class _ServerItem(ListItem):
    def __init__(self, server: dict[str, Any]):
        self.server = server
        name = server.get("display_name") or server.get("name")
        label = f"{name}  [dim]{server.get('command_summary', '')}[/]"
        super().__init__(Label(label, markup=True))


class _ToolItem(ListItem):
    def __init__(self, tool: dict[str, Any]):
        self.tool = tool
        kind = tool.get("kind", "unknown")
        name = tool.get("name", "")
        super().__init__(Label(f"[cyan]{kind}[/] {name}"))


class McpDrawerModal(ModalScreen[dict[str, Any] | None]):
    """Discover MCP servers, opt-in connect, inspect tools, confirm tool calls."""

    DEFAULT_CSS = """
    McpDrawerModal {
        align: center middle;
    }
    #mcp-box {
        width: 88;
        max-width: 95;
        height: 24;
        border: solid #9a7b3c;
        background: #1a1510;
        padding: 1 1;
    }
    #mcp-servers, #mcp-tools {
        height: 1fr;
        border: solid #3d352a;
        margin: 0 1;
    }
    #mcp-detail, #mcp-result {
        height: auto;
        max-height: 6;
        margin: 1 0;
        padding: 0 1;
    }
    #mcp-payload {
        margin: 1 0;
    }
    Button {
        margin: 0 1 0 0;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, query: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._query = query
        self._selected_server_id: str = ""
        self._selected_tool: dict[str, Any] = {}
        self._pending_confirm = False

    def compose(self) -> ComposeResult:
        with Container(id="mcp-box"):
            yield Label("Jeles // MCP Drawer", id="mcp-title")
            yield Static(
                "Discover servers only — connect explicitly for this session. Tool calls require confirmation.",
                id="mcp-help",
            )
            with Horizontal():
                yield ListView(id="mcp-servers")
                yield ListView(id="mcp-tools")
            yield Static("", id="mcp-detail", markup=True)
            yield Input(placeholder='Tool payload JSON, e.g. {"query": "..."}', id="mcp-payload")
            with Horizontal():
                yield Button("Connect", id="btn-connect", variant="primary")
                yield Button("Disconnect", id="btn-disconnect")
                yield Button("Run tool", id="btn-run", variant="warning")
                yield Button("Confirm", id="btn-confirm", variant="error")
            yield Static("", id="mcp-result", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_servers()

    def _refresh_servers(self) -> None:
        lv = self.query_one("#mcp-servers", ListView)
        lv.clear()
        for server in _mcp_registry.list_available_servers():
            lv.append(_ServerItem(server))
        connected = _mcp_generic.connected_servers()
        if connected:
            names = ", ".join(c["name"] for c in connected)
            self.query_one("#mcp-detail", Static).update(f"[green]Connected:[/] {names}")
        else:
            self.query_one("#mcp-detail", Static).update("[dim]No MCP servers connected this session.[/]")

    def _selected_server(self) -> dict[str, Any] | None:
        lv = self.query_one("#mcp-servers", ListView)
        item = lv.highlighted_child
        if isinstance(item, _ServerItem):
            return item.server
        return None

    def _selected_tool_dict(self) -> dict[str, Any] | None:
        lv = self.query_one("#mcp-tools", ListView)
        item = lv.highlighted_child
        if isinstance(item, _ToolItem):
            return item.tool
        return self._selected_tool or None

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, _ServerItem):
            s = event.item.server
            self._selected_server_id = s.get("server_id", "")
            self.query_one("#mcp-detail", Static).update(
                f"[bold]{s.get('display_name') or s.get('name')}[/] · {s.get('origin_label', '')}\n"
                f"{s.get('config_path')}\n"
                f"[dim]{s.get('command_summary')}[/]"
            )
            self._load_tools_for_server(self._selected_server_id)
        elif isinstance(event.item, _ToolItem):
            tool = _mcp_adapters.tool_record(event.item.tool)
            self._selected_tool = tool
            payload = _mcp_adapters.default_payload(tool, self._query)
            self.query_one("#mcp-payload", Input).value = json.dumps(payload, ensure_ascii=False)
            self.query_one("#mcp-detail", Static).update(
                f"[bold]{tool.get('name')}[/] [{tool.get('kind')}]\n{tool.get('description', '')[:200]}"
            )

    @work(exclusive=True, thread=True)
    def _connect_worker(self, server_id: str) -> None:
        result = _mcp_generic.connect_server(server_id)
        self.app.call_from_thread(self._after_connect, result)

    def _after_connect(self, result: dict[str, Any]) -> None:
        if result.get("ok"):
            self.notify(f"Connected MCP: {result.get('name')}", timeout=3)
            self._load_tools_for_server(result.get("server_id", ""))
        else:
            self.notify(f"MCP connect failed: {result.get('error')}", severity="error", timeout=6)
        self._refresh_servers()

    def _load_tools_for_server(self, server_id: str) -> None:
        tools_lv = self.query_one("#mcp-tools", ListView)
        tools_lv.clear()
        if not server_id:
            return
        for tool in _mcp_generic.list_server_tools(server_id):
            tools_lv.append(_ToolItem(_mcp_adapters.tool_record(tool)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-connect":
            server = self._selected_server()
            if not server:
                self.notify("Select a server first.", severity="warning")
                return
            self._connect_worker(server["server_id"])
        elif event.button.id == "btn-disconnect":
            server = self._selected_server()
            if not server:
                self.notify("Select a server first.", severity="warning")
                return
            _mcp_generic.disconnect_server(server["server_id"])
            self._refresh_servers()
            self.query_one("#mcp-tools", ListView).clear()
            self.notify(f"Disconnected {server.get('name')}", timeout=2)
        elif event.button.id == "btn-run":
            self._prepare_run()
        elif event.button.id == "btn-confirm":
            server = self._selected_server()
            tool = self._selected_tool_dict()
            if not server or not tool:
                self.notify("Select a server and tool.", severity="warning")
                return
            raw = self.query_one("#mcp-payload", Input).value.strip()
            try:
                payload = json.loads(raw) if raw else _mcp_adapters.default_payload(tool, self._query)
            except json.JSONDecodeError as exc:
                self.notify(f"Invalid JSON payload: {exc}", severity="error")
                return
            self._execute_confirmed(server, tool, payload)

    def _prepare_run(self) -> None:
        server = self._selected_server()
        tool = self._selected_tool_dict()
        if not server or not tool:
            self.notify("Select a connected server and tool.", severity="warning")
            return
        if server["server_id"] not in {c["server_id"] for c in _mcp_generic.connected_servers()}:
            self.notify("Connect to this server first.", severity="warning")
            return
        kind = tool.get("kind", "unknown")
        self._pending_confirm = True
        self.query_one("#mcp-result", Static).update(
            f"[yellow]Confirm tool call?[/]\n"
            f"Server: {server.get('name')} · Tool: {tool.get('name')} · Kind: {kind}\n"
            f"Press [bold]Confirm[/] to run, Esc to cancel."
        )

    @work(exclusive=True, thread=True)
    def _execute_confirmed(
        self,
        server: dict[str, Any],
        tool: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        if not self._pending_confirm:
            self.app.call_from_thread(
                self.notify, "Press Run tool first.", severity="warning"
            )
            return
        result = _mcp_generic.call_tool_confirmed(
            server["server_id"],
            str(tool.get("name")),
            payload,
            confirmed=True,
        )
        self.app.call_from_thread(self._show_tool_result, result)

    def _show_tool_result(self, result: dict[str, Any]) -> None:
        self._pending_confirm = False
        pane = self.query_one("#mcp-result", Static)
        if not result.get("ok"):
            pane.update(f"[red]{result.get('error') or 'tool call failed'}[/]")
            return
        body = result.get("result")
        if isinstance(body, (dict, list)):
            text = json.dumps(body, ensure_ascii=False, indent=2)
        else:
            text = str(body)
        pane.update(text[:1800])

    def action_dismiss_modal(self) -> None:
        self.dismiss({"connected": _mcp_generic.connected_servers()})
