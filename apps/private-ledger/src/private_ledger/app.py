# b17: 67F26  ΔΣ=42
import os
from datetime import date
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
)

from .db import LedgerDB
from .llm import DEFAULT_MODEL, parse_transaction, stream_insights
from .schema import init_ledger

DB_PATH = os.environ.get("LEDGER_DB", str(Path.home() / ".willow" / "private-ledger.db"))


# ── Insights modal ────────────────────────────────────────────────────────────

class InsightsScreen(ModalScreen):
    CSS = """
    InsightsScreen {
        align: center middle;
        background: $background 60%;
    }
    #insights-panel {
        width: 82%;
        height: 78%;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    #insights-title {
        margin-bottom: 1;
        text-style: bold;
        color: $accent;
    }
    #chat-log {
        height: 1fr;
        border: solid $surface-lighten-2;
        padding: 0 1;
        margin-bottom: 1;
    }
    #insights-hint {
        height: 1;
        color: $text-muted;
        margin-bottom: 0;
    }
    """
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, db: LedgerDB, model: str = DEFAULT_MODEL):
        super().__init__()
        self.db = db
        self.model = model

    def compose(self) -> ComposeResult:
        with Vertical(id="insights-panel"):
            yield Label("Ledger Insights  ·  powered by yggdrasil:v9", id="insights-title")
            yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
            yield Label("[dim]Esc to close[/dim]", id="insights-hint")
            yield Input(
                placeholder="Where am I overspending? / Summarize May / What can I cut?",
                id="insights-input",
            )

    def on_mount(self):
        log = self.query_one("#chat-log", RichLog)
        log.write("[dim]Ask me anything about your transactions and budget.[/dim]")
        self.query_one("#insights-input").focus()

    @on(Input.Submitted, "#insights-input")
    def handle_question(self, event: Input.Submitted):
        question = event.value.strip()
        if not question:
            return
        event.input.value = ""
        log = self.query_one("#chat-log", RichLog)
        log.write(f"\n[bold cyan]You:[/bold cyan] {question}")
        log.write("[bold yellow]Yggdrasil:[/bold yellow] [dim]thinking…[/dim]")
        self._ask(question)

    @work
    async def _ask(self, question: str):
        log = self.query_one("#chat-log", RichLog)
        tx_text = self.db.get_recent_transactions_text()
        today = date.today()
        budget = self.db.get_budget_summary(today.year, today.month)
        budget_text = "\n".join(
            f"{cat}: spent ${v['spent']:.2f} of ${v['budget']:.2f} ({v['pct']:.0f}%)"
            for cat, v in budget.items()
            if v["budget"]
        ) or "(no budget configured)"

        try:
            chunks = []
            async for token in stream_insights(question, tx_text, budget_text, self.model):
                chunks.append(token)
            response = "".join(chunks).strip()
            # overwrite the "thinking…" line — just write the response
            log.write(f"[bold yellow]Yggdrasil:[/bold yellow] {response}")
        except Exception as exc:
            log.write(f"[red]Error: {exc}[/red]")


# ── Add Account modal ─────────────────────────────────────────────────────────

class AddAccountScreen(ModalScreen[bool]):
    CSS = """
    AddAccountScreen {
        align: center middle;
        background: $background 60%;
    }
    #acct-panel {
        width: 52;
        height: auto;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    #acct-title {
        margin-bottom: 1;
        text-style: bold;
        color: $accent;
    }
    .acct-label {
        margin-top: 1;
        color: $text-muted;
    }
    #acct-hint {
        margin-top: 1;
        color: $text-muted;
    }
    """
    BINDINGS = [Binding("escape", "dismiss_false", "Cancel")]

    def __init__(self, db: LedgerDB):
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        with Vertical(id="acct-panel"):
            yield Label("Add Account", id="acct-title")
            yield Label("Name", classes="acct-label")
            yield Input(placeholder="Checking, Savings…", id="acct-name")
            yield Label("Type", classes="acct-label")
            yield Select(
                [("Checking", "checking"), ("Savings", "savings"),
                 ("Credit Card", "credit"), ("Cash", "cash")],
                id="acct-type",
                value="checking",
            )
            yield Label("Starting balance", classes="acct-label")
            yield Input(placeholder="0.00", id="acct-balance")
            yield Label("[dim]Enter to save · Esc to cancel[/dim]", id="acct-hint")

    def on_mount(self):
        self.query_one("#acct-name").focus()

    @on(Input.Submitted, "#acct-balance")
    def save(self, _=None):
        name = self.query_one("#acct-name", Input).value.strip()
        type_ = self.query_one("#acct-type", Select).value
        balance_str = self.query_one("#acct-balance", Input).value.strip() or "0"
        if not name:
            return
        try:
            balance = float(balance_str.replace("$", "").replace(",", ""))
        except ValueError:
            balance = 0.0
        self.db.add_account(name, str(type_), balance)
        self.dismiss(True)

    @on(Input.Submitted, "#acct-name")
    def focus_balance(self, _=None):
        self.query_one("#acct-balance").focus()

    def action_dismiss_false(self):
        self.dismiss(False)


# ── Main app ──────────────────────────────────────────────────────────────────

class LedgerApp(App):
    TITLE = "Ledger"
    SUB_TITLE = "personal finance + yggdrasil"

    CSS = """
    Screen { layers: base overlay; }

    #body { height: 1fr; }

    #sidebar {
        width: 28;
        border-right: solid $accent-darken-2;
        padding: 1 1;
        overflow-y: auto;
    }

    .section-label {
        color: $accent;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    #main { width: 1fr; }

    #tx-table { height: 1fr; }

    #status-bar {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }

    #nl-input { border: tall $accent; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("i", "insights", "Insights"),
        Binding("a", "add_account", "Add account"),
        Binding("d", "delete_tx", "Delete"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "cancel", show=False),
    ]

    def __init__(self, db_path: str = DB_PATH):
        super().__init__()
        init_ledger(db_path)
        self.db = LedgerDB(db_path)
        self._pending: dict | None = None

    # ── Layout ─────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("ACCOUNTS", classes="section-label")
                yield Static(id="accounts-list")
                yield Label("BUDGET", classes="section-label", id="budget-label")
                yield ScrollableContainer(Static(id="budget-bars"))
            with Vertical(id="main"):
                yield DataTable(id="tx-table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="status-bar")
                yield Input(
                    placeholder='> "spent $40 on gas" · "got paid $2000" · Enter to parse',
                    id="nl-input",
                )
        yield Footer()

    def on_mount(self):
        table = self.query_one("#tx-table", DataTable)
        table.add_columns("Date", "Account", "Description", "Category", "Amount")
        today = date.today()
        self.query_one("#budget-label").update(f"{today.strftime('%B').upper()} BUDGET")
        self._refresh_all()

    # ── Data loading ───────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._load_transactions()
        self._load_accounts()
        self._load_budget()

    def _load_transactions(self):
        table = self.query_one("#tx-table", DataTable)
        table.clear()
        for tx in self.db.get_transactions():
            amt = tx["amount"]
            if amt > 0:
                amt_str = f"[green]+${amt:,.2f}[/green]"
            else:
                amt_str = f"[red]-${abs(amt):,.2f}[/red]"
            table.add_row(
                tx["date"],
                tx["account_name"] or "—",
                tx["description"],
                tx["category"] or "Other",
                amt_str,
                key=str(tx["id"]),
            )

    def _load_accounts(self):
        accounts = self.db.get_accounts()
        if not accounts:
            text = "[dim]No accounts\nPress 'a' to add one[/dim]"
        else:
            parts = []
            for acc in accounts:
                color = "green" if acc["balance"] >= 0 else "red"
                parts.append(
                    f"[bold]{acc['name']}[/bold]\n"
                    f"  [{color}]${acc['balance']:,.2f}[/] [dim]{acc['type']}[/dim]"
                )
            text = "\n\n".join(parts)
        self.query_one("#accounts-list", Static).update(text)

    def _load_budget(self):
        today = date.today()
        budget = self.db.get_budget_summary(today.year, today.month)
        lines = []
        for cat, v in sorted(budget.items()):
            if not v["budget"]:
                continue
            pct = v["pct"]
            color = "green" if pct < 70 else "yellow" if pct < 90 else "red"
            bar_len = 16
            filled = min(int(pct / 100 * bar_len), bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            cat_short = cat[:13]
            lines.append(f"[dim]{cat_short}[/dim]\n[{color}]{bar}[/] {pct:.0f}%")
        self.query_one("#budget-bars", Static).update(
            "\n\n".join(lines) or "[dim]No spending data yet[/dim]"
        )

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _status(self, msg: str):
        self.query_one("#status-bar", Static).update(msg)

    # ── NL input ───────────────────────────────────────────────────────────────

    @on(Input.Submitted, "#nl-input")
    def handle_nl(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return

        if self._pending is not None:
            # second enter: confirm save
            event.input.value = ""
            self._commit_pending()
            return

        event.input.value = ""
        self._status("[dim]Parsing…[/dim]")
        self._parse(text)

    @work
    async def _parse(self, text: str):
        try:
            result = await parse_transaction(text, date.today().isoformat())
        except Exception as exc:
            self._status(f"[red]LLM error: {exc}[/red]")
            return

        if "error" in result:
            self._status(f"[red]Could not parse:[/red] {text}")
            return

        self._pending = result
        amt = result.get("amount", 0.0)
        sign = "+" if amt > 0 else ""
        self._status(
            f"[yellow]Preview:[/yellow]  {result.get('date')}  ·  "
            f"{result.get('description')}  ·  {result.get('category')}  ·  "
            f"[bold]{sign}{amt:.2f}[/bold]"
            f"   [dim]Enter to save  ·  Esc to cancel[/dim]"
        )

    def _commit_pending(self):
        tx = self._pending
        self._pending = None
        if tx is None:
            return
        accounts = self.db.get_accounts()
        account_id = accounts[0]["id"] if accounts else None
        self.db.add_transaction(
            account_id=account_id,
            date=tx.get("date", date.today().isoformat()),
            amount=tx.get("amount", 0.0),
            description=tx.get("description", "Unknown"),
            category=tx.get("category", "Other"),
        )
        self._status(f"[green]Saved:[/green] {tx.get('description')}")
        self._refresh_all()

    # ── Actions ────────────────────────────────────────────────────────────────

    def action_cancel(self):
        if self._pending is not None:
            self._pending = None
            self._status("[dim]Cancelled[/dim]")

    def action_insights(self):
        self.push_screen(InsightsScreen(self.db))

    def action_add_account(self):
        def on_result(saved: bool):
            if saved:
                self._refresh_all()

        self.push_screen(AddAccountScreen(self.db), on_result)

    def action_delete_tx(self):
        table = self.query_one("#tx-table", DataTable)
        if table.row_count == 0:
            return
        try:
            coord = table.cursor_coordinate
            cell_key = table.coordinate_to_cell_key(coord)
            row_key = cell_key.row_key.value
            tx_id = int(row_key)
            self.db.delete_transaction(tx_id)
            self._status("[dim]Transaction deleted[/dim]")
            self._refresh_all()
        except Exception as exc:
            self._status(f"[red]Delete failed: {exc}[/red]")

    def action_refresh(self):
        self._refresh_all()
        self._status("[dim]Refreshed[/dim]")


def main():
    LedgerApp().run()


if __name__ == "__main__":
    main()
