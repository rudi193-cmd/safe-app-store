#!/usr/bin/env python3
"""SAFE App Store — browse, install, and manage SAFE apps."""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import traceback
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static

import store_mcp

_DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(_DATA_DIR / "store_tui.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_log = logging.getLogger("store_tui")

_REPO_ROOT = pathlib.Path(__file__).resolve().parent
_CATALOG_PATH = _REPO_ROOT / "catalog.json"
_CONSENT_PATH = _DATA_DIR / "store_consent.json"
_SAFE_APPS_ROOT = pathlib.Path.home() / "github" / "SAFE" / "Applications"

_STATUS_COLOR = {
    "stable": "green",
    "beta": "yellow",
    "coming_soon": "dim",
    "archived": "dim",
}
_STATUS_BADGE = {
    "stable": "● stable",
    "beta": "◑ beta",
    "coming_soon": "○ soon",
    "archived": "✕ arch",
}
_PERM_LABEL = {
    "file_read": "Read files on your device",
    "file_write": "Write files on your device",
    "store_read": "Read the app catalog",
    "store_write": "Modify the app catalog",
    "postgres_read": "Read from local database",
    "postgres_write": "Write to local database",
    "knowledge_write": "Write to knowledge base",
    "knowledge_read": "Read knowledge base",
    "local_llm": "Use local AI models",
    "task_submit": "Submit background tasks",
    "pipeline": "Run data pipelines",
    "filesystem_write": "Write to filesystem",
    "filesystem_read": "Read filesystem",
    "willow_kb_read": "Read Willow knowledge base",
    "willow_kb_write": "Write to Willow knowledge base",
    "network_read": "Fetch data from the internet",
    "jeles_fetch": "Query semantic memory",
    "jeles_write": "Write to semantic memory",
}


def _perm_label(perm: str) -> str:
    return _PERM_LABEL.get(perm, perm)


def _load_catalog() -> list[dict]:
    if not _CATALOG_PATH.exists():
        return []
    try:
        return json.loads(_CATALOG_PATH.read_text()).get("apps", [])
    except Exception:
        return []


def _load_manifest(app_id: str) -> dict | None:
    p = _REPO_ROOT / "apps" / app_id / "safe-app-manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None


def _load_consent() -> dict:
    if not _CONSENT_PATH.exists():
        return {}
    try:
        return json.loads(_CONSENT_PATH.read_text())
    except Exception:
        return {}


def _save_consent(consent: dict) -> None:
    _CONSENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONSENT_PATH.write_text(json.dumps(consent, indent=2))


def _check_installed_locally(app_id: str) -> bool:
    return (_SAFE_APPS_ROOT / app_id).is_dir()


class ConsentModal(ModalScreen):
    """Shows app permissions before installing."""

    DEFAULT_CSS = """
    ConsentModal {
        align: center middle;
    }
    #consent-dialog {
        background: $surface;
        border: solid $primary;
        padding: 2 3;
        width: 64;
        height: auto;
        max-height: 32;
    }
    #consent-title {
        text-style: bold;
        margin-bottom: 1;
        color: $foreground;
    }
    #consent-body {
        margin-bottom: 1;
    }
    #consent-buttons {
        margin-top: 1;
        height: 3;
    }
    #consent-accept {
        margin-right: 3;
        background: $success;
        color: $foreground;
    }
    """

    def __init__(self, app_data: dict, manifest: dict | None) -> None:
        super().__init__()
        self._app_data = app_data
        self._manifest = manifest or {}

    def compose(self) -> ComposeResult:
        app = self._app_data
        manifest = self._manifest
        lines: list[str] = []

        permissions = manifest.get("permissions", [])
        if permissions:
            lines.append("[bold]PERMISSIONS[/bold]")
            for perm in permissions:
                lines.append(f"  ◆ {_perm_label(perm)}")
            lines.append("")
        else:
            lines.append("[dim]No special permissions required.[/dim]")
            lines.append("")

        streams = manifest.get("data_streams", [])
        if streams:
            lines.append("[bold]DATA STORED[/bold]")
            for s in streams:
                retention = s.get("retention", "?")
                sid = s.get("id", "?")
                desc = s.get("description", "")
                lines.append(f"  ◆ [dim]{sid}[/dim]  [{retention}]")
                if desc:
                    lines.append(f"    [dim]{desc[:80]}[/dim]")
            lines.append("")

        tier = manifest.get("privacy_tier", "unknown")
        local_pct = int(manifest.get("local_processing", 0) * 100)
        p_color = "green" if tier in ("client_only", "local") else "yellow"
        lines.append(
            f"[bold]Privacy:[/bold] [{p_color}]{tier}[/{p_color}]  ·  {local_pct}% local"
        )

        with Vertical(id="consent-dialog"):
            yield Static(
                f"[bold]{app.get('name', app.get('id', '?'))}[/bold] is requesting:",
                id="consent-title",
                markup=True,
            )
            yield Static("\n".join(lines), id="consent-body", markup=True)
            with Horizontal(id="consent-buttons"):
                yield Button("Accept & Install", id="consent-accept")
                yield Button("Cancel", id="consent-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "consent-accept")


class ConfirmModal(ModalScreen):
    """Yes/No confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    #confirm-dialog {
        background: $surface;
        border: solid $error;
        padding: 2 3;
        width: 52;
        height: auto;
    }
    #confirm-buttons {
        margin-top: 1;
        height: 3;
    }
    #confirm-yes {
        background: $error;
        margin-right: 3;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self._message, markup=True)
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes, uninstall", id="confirm-yes")
                yield Button("Cancel", id="confirm-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class StoreApp(App):
    """SAFE App Store — browse, install, and manage SAFE apps."""

    TITLE = "SAFE App Store"
    SUB_TITLE = "local-first · yours to keep"

    CSS = """
    Screen { background: $surface; }

    #main { height: 1fr; }

    #sidebar {
        width: 40;
        background: $panel;
        border-right: solid $primary-darken-2;
    }

    #filter-bar {
        height: 3;
        padding: 1 1 0 1;
        background: $panel-darken-1;
    }

    .filt {
        background: $panel-darken-1;
        border: none;
        height: 1;
        min-width: 1;
        padding: 0 1;
        margin: 0 1 0 0;
        color: $text-muted;
    }

    .filt.on {
        color: $primary;
        text-style: bold underline;
        background: $panel-darken-1;
    }

    #search {
        margin: 0 1;
        height: 3;
        background: $panel;
        border: solid $primary-darken-2;
    }

    #app-list {
        height: 1fr;
        background: $panel;
        border: none;
        padding: 0;
    }

    #app-list > ListItem {
        background: $panel;
        padding: 0 1;
        height: 3;
        border-bottom: solid $panel-darken-1;
    }

    #app-list > ListItem.--highlight {
        background: $primary-darken-3;
    }

    #detail {
        padding: 1 2;
        background: $surface;
    }

    #detail-content {
        margin-bottom: 1;
    }

    #action-bar {
        height: 3;
        margin-top: 1;
        padding: 0;
    }

    #btn-install {
        background: $success;
        margin-right: 2;
    }

    #btn-uninstall {
        background: $error;
        margin-right: 2;
    }

    #launch-hint {
        color: $text-muted;
        padding: 0 1;
    }

    .gone { display: none; }

    #status-bar {
        height: 1;
        background: $panel-darken-2;
        padding: 0 2;
        color: $text-muted;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "focus_search", "Search", show=False),
        Binding("escape", "clear_search", "Clear search", show=False),
        Binding("1", "filter('all')", "All", show=False),
        Binding("2", "filter('installed')", "Installed", show=False),
        Binding("3", "filter('available')", "Available", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._catalog: list[dict] = []
        self._manifests: dict[str, dict] = {}
        self._installed: set[str] = set()
        self._consent: dict = {}
        self._filter = "all"
        self._search = ""
        self._selected: str | None = None
        self._mcp_ok = False

    # ── compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                with Horizontal(id="filter-bar"):
                    yield Button("All", id="filt-all", classes="filt on")
                    yield Button("Installed", id="filt-installed", classes="filt")
                    yield Button("Available", id="filt-available", classes="filt")
                yield Input(placeholder="/ to search...", id="search")
                yield ListView(id="app-list")
            with ScrollableContainer(id="detail"):
                yield Static(
                    "[dim]Select an app from the list.[/dim]",
                    id="detail-content",
                    markup=True,
                )
                with Horizontal(id="action-bar"):
                    yield Button("Install", id="btn-install", classes="gone")
                    yield Button("Uninstall", id="btn-uninstall", classes="gone")
                    yield Static("", id="launch-hint", markup=True)
        yield Static("Loading...", id="status-bar")
        yield Footer()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        self._catalog = _load_catalog()
        self._consent = _load_consent()
        for app in self._catalog:
            m = _load_manifest(app["id"])
            if m:
                self._manifests[app["id"]] = m
        for app in self._catalog:
            if _check_installed_locally(app["id"]):
                self._installed.add(app["id"])
        self._rebuild_list()
        self._update_status(f"Loaded {len(self._catalog)} apps · connecting to Willow...")
        asyncio.create_task(self._connect_mcp())

    async def _connect_mcp(self) -> None:
        try:
            ok = await asyncio.to_thread(store_mcp.ensure_started, 30)
            self._mcp_ok = ok
            if ok:
                await self._refresh_installed_from_mcp()
            else:
                self._update_status(
                    f"Willow offline ({store_mcp._mcp_error or 'timeout'}) · local state shown"
                )
        except Exception as exc:
            _log.error("MCP connect: %s", exc)
            self._update_status(f"Willow error: {exc}")

    async def _refresh_installed_from_mcp(self) -> None:
        try:
            apps = await asyncio.to_thread(store_mcp.app_list)
            ids = {
                (a.get("app_id") or a.get("id") or "")
                for a in (apps or [])
                if (a.get("app_id") or a.get("id"))
            }
            self._installed = ids
            self._rebuild_list()
            if self._selected:
                self._show_detail(self._selected)
        except Exception as exc:
            _log.warning("app_list: %s", exc)
        self._update_status(self._status_line())

    # ── list building ─────────────────────────────────────────────────────────

    def _filtered_apps(self) -> list[dict]:
        apps = self._catalog
        if self._filter == "installed":
            apps = [a for a in apps if a["id"] in self._installed]
        elif self._filter == "available":
            apps = [
                a for a in apps
                if a["id"] not in self._installed and a.get("status") != "archived"
            ]
        else:
            apps = [a for a in apps if a.get("status") != "archived"]
        if self._search:
            q = self._search.lower()
            apps = [
                a for a in apps
                if q in a.get("name", "").lower()
                or q in a.get("description", "").lower()
                or any(q in t for t in a.get("tags", []))
            ]
        return apps

    def _rebuild_list(self) -> None:
        try:
            lv = self.query_one("#app-list", ListView)
        except Exception:
            return
        apps = self._filtered_apps()
        lv.clear()
        for app in apps:
            aid = app["id"]
            status = app.get("status", "")
            installed = aid in self._installed
            dot = "[green]●[/green]" if installed else "[dim]○[/dim]"
            col = _STATUS_COLOR.get(status, "dim")
            badge = f"[{col}]{_STATUS_BADGE.get(status, status):<7}[/{col}]"
            name = app.get("name", aid)
            if len(name) > 22:
                name = name[:20] + "…"
            markup = f"{dot} {name:<22} {badge}"
            lv.append(ListItem(Label(markup, markup=True), name=aid))
        count = len(apps)
        self._update_status(
            self._status_line()
            + (f"  ·  showing {count}" if self._search else "")
        )

    # ── detail panel ─────────────────────────────────────────────────────────

    def _show_detail(self, app_id: str) -> None:
        app = next((a for a in self._catalog if a["id"] == app_id), None)
        if not app:
            return
        manifest = self._manifests.get(app_id)
        installed = app_id in self._installed
        consent_rec = self._consent.get(app_id)
        status = app.get("status", "")
        col = _STATUS_COLOR.get(status, "dim")
        badge = f"[{col}]{_STATUS_BADGE.get(status, status)}[/{col}]"

        lines: list[str] = [
            f"[bold]{app.get('name', app_id)}[/bold]   {badge}",
            "",
            app.get("description", "No description."),
            "",
        ]

        meta: list[str] = [f"[dim]Author:[/dim] {app.get('author', '—')}"]
        if manifest:
            tier = manifest.get("privacy_tier", "—")
            pct = int(manifest.get("local_processing", 0) * 100)
            p_col = "green" if tier in ("client_only", "local") else "yellow"
            meta.append(f"[dim]Privacy:[/dim] [{p_col}]{tier}[/{p_col}]")
            meta.append(f"[dim]Local:[/dim] {pct}%")
        lines.append("  ·  ".join(meta))

        tags = app.get("tags", [])
        if tags:
            lines.append("[dim]Tags:[/dim] " + "  ·  ".join(tags))

        lines += ["", "─" * 52, ""]

        if manifest:
            perms = manifest.get("permissions", [])
            if perms:
                lines.append("[bold]PERMISSIONS[/bold]")
                for p in perms:
                    lines.append(f"  ◆ [dim]{p:<20}[/dim] {_perm_label(p)}")
                lines.append("")

            streams = manifest.get("data_streams", [])
            if streams:
                lines.append("[bold]DATA STORED[/bold]")
                for s in streams:
                    sid = s.get("id", "?")
                    ret = s.get("retention", "?")
                    desc = s.get("description", "")
                    lines.append(f"  ◆ [dim]{sid}[/dim]  [{ret}]")
                    if desc:
                        lines.append(f"    [dim]{desc[:80]}[/dim]")
                lines.append("")
            lines += ["─" * 52, ""]

        if consent_rec:
            date = consent_rec.get("consented_at", "")[:10]
            lines.append(f"[bold]CONSENT[/bold]  [green]✓ Granted {date}[/green]")
        elif installed:
            lines.append("[bold]CONSENT[/bold]  [dim]Installed (no consent record)[/dim]")
        else:
            lines.append("[bold]CONSENT[/bold]  [dim]Not consented[/dim]")

        try:
            self.query_one("#detail-content", Static).update("\n".join(lines))
        except Exception as exc:
            _log.warning("detail update: %s", exc)

        try:
            inst_btn = self.query_one("#btn-install", Button)
            unin_btn = self.query_one("#btn-uninstall", Button)
            hint = self.query_one("#launch-hint", Static)

            if status == "archived":
                inst_btn.add_class("gone")
                unin_btn.add_class("gone")
                hint.update("[dim]Archived — not available for install[/dim]")
            elif installed:
                inst_btn.add_class("gone")
                unin_btn.remove_class("gone")
                hint.update(f"[dim]make run app={app_id}[/dim]")
            else:
                inst_btn.remove_class("gone")
                unin_btn.add_class("gone")
                hint.update("")
        except Exception as exc:
            _log.warning("action bar: %s", exc)

    # ── events ────────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        app_id = event.item.name
        if app_id:
            self._selected = app_id
            self._show_detail(app_id)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        try:
            if bid == "filt-all":
                self._set_filter("all")
            elif bid == "filt-installed":
                self._set_filter("installed")
            elif bid == "filt-available":
                self._set_filter("available")
            elif bid == "btn-install" and self._selected:
                await self._do_install(self._selected)
            elif bid == "btn-uninstall" and self._selected:
                await self._do_uninstall(self._selected)
        except Exception as exc:
            _log.error("button %s: %s\n%s", bid, exc, traceback.format_exc())
            self._update_status(f"Error: {exc}")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._search = event.value
        self._rebuild_list()

    # ── filter ────────────────────────────────────────────────────────────────

    def _set_filter(self, f: str) -> None:
        self._filter = f
        for fid, fname in [
            ("filt-all", "all"),
            ("filt-installed", "installed"),
            ("filt-available", "available"),
        ]:
            try:
                btn = self.query_one(f"#{fid}", Button)
                if fname == f:
                    btn.add_class("on")
                else:
                    btn.remove_class("on")
            except Exception:
                pass
        self._rebuild_list()

    # ── install / uninstall ───────────────────────────────────────────────────

    async def _do_install(self, app_id: str) -> None:
        app = next((a for a in self._catalog if a["id"] == app_id), None)
        if not app:
            return
        manifest = self._manifests.get(app_id)

        accepted: bool = await self.push_screen_wait(ConsentModal(app, manifest))
        if not accepted:
            return

        name = app.get("name", app_id)
        self._update_status(f"Installing {name}...")
        try:
            await asyncio.to_thread(store_mcp.app_install, app_id, "monorepo")
            msg = f"Installed {name}"
        except Exception as exc:
            _log.error("install %s: %s", app_id, exc)
            msg = f"Consent recorded — Willow: {exc}"

        self._installed.add(app_id)
        self._consent[app_id] = {
            "consented_at": datetime.now(timezone.utc).isoformat(),
            "permissions": (manifest or {}).get("permissions", []),
        }
        _save_consent(self._consent)
        self._rebuild_list()
        self._show_detail(app_id)
        self._update_status(msg)

    async def _do_uninstall(self, app_id: str) -> None:
        app = next((a for a in self._catalog if a["id"] == app_id), None)
        name = app.get("name", app_id) if app else app_id

        confirmed: bool = await self.push_screen_wait(
            ConfirmModal(f"Uninstall [bold]{name}[/bold]?")
        )
        if not confirmed:
            return

        self._update_status(f"Uninstalling {name}...")
        try:
            await asyncio.to_thread(store_mcp.app_uninstall, app_id)
        except Exception as exc:
            _log.warning("uninstall %s: %s", app_id, exc)

        self._installed.discard(app_id)
        self._consent.pop(app_id, None)
        _save_consent(self._consent)
        self._rebuild_list()
        self._show_detail(app_id)
        self._update_status(f"Uninstalled {name}")

    # ── status bar ────────────────────────────────────────────────────────────

    def _status_line(self) -> str:
        n_inst = len(self._installed)
        n_total = len([a for a in self._catalog if a.get("status") != "archived"])
        mcp = "willow: ready" if self._mcp_ok else "willow: offline"
        return f"{mcp}  ·  {n_inst} installed  ·  {n_total} apps  ·  / search  Q quit"

    def _update_status(self, msg: str) -> None:
        try:
            self.query_one("#status-bar", Static).update(msg)
        except Exception:
            pass

    # ── actions ───────────────────────────────────────────────────────────────

    def action_focus_search(self) -> None:
        try:
            self.query_one("#search", Input).focus()
        except Exception:
            pass

    def action_clear_search(self) -> None:
        try:
            inp = self.query_one("#search", Input)
            inp.value = ""
            self._search = ""
            self._rebuild_list()
            self.query_one("#app-list", ListView).focus()
        except Exception:
            pass

    def action_filter(self, name: str) -> None:
        self._set_filter(name)


def main() -> None:
    StoreApp().run()


if __name__ == "__main__":
    main()
