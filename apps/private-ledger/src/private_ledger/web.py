# b17: PLWEB  ΔΣ=42
"""
web.py — the on-device human mirror for Private Ledger. b17: PLWEB

Pattern (oakenscrolls-office/web.py, verbatim in spirit): routing is a pure
function — handle(method, path, db, today) -> (status, content_type, body) — so
the whole surface is unit-testable without a socket. serve() adapts it to
http.server for real use. Localhost only; this is a mirror, not a service. It is
strictly READ-ONLY: it never mutates the ledger.

Usage:
  python3 -m private_ledger --web            # http://127.0.0.1:8770
  python3 -m private_ledger --web --port N
"""
from __future__ import annotations

import json
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import subscriptions
from .db import LedgerDB

_HTML = "text/html; charset=utf-8"
_JSON = "application/json"
PORT = 8770


# ── Data assembly (read-only) ─────────────────────────────────────────────────

def _rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def _collect(db: LedgerDB, today: date) -> dict:
    accounts = _rows_to_dicts(db.get_accounts())
    transactions = _rows_to_dicts(db.get_transactions(limit=500))
    budget = db.get_budget_summary(today.year, today.month)
    subs = subscriptions.detect_subscriptions(transactions, today)
    total_balance = sum(a.get("balance", 0.0) or 0.0 for a in accounts)
    return {
        "today": today.isoformat(),
        "total_balance": total_balance,
        "accounts": accounts,
        "transactions": transactions,
        "budget": budget,
        "subscriptions": subs,
        "cashflow": _monthly_cashflow(transactions),
    }


def _monthly_cashflow(transactions: list[dict]) -> list[dict]:
    """Sum money-in vs money-out per YYYY-MM, oldest first."""
    buckets: dict[str, dict[str, float]] = {}
    for tx in transactions:
        raw = tx.get("date") or ""
        month = str(raw)[:7]
        if len(month) != 7:
            continue
        amt = float(tx.get("amount", 0.0) or 0.0)
        slot = buckets.setdefault(month, {"in": 0.0, "out": 0.0})
        if amt >= 0:
            slot["in"] += amt
        else:
            slot["out"] += -amt
    return [
        {"month": m, "in": round(v["in"], 2), "out": round(v["out"], 2)}
        for m, v in sorted(buckets.items())
    ]


# ── SVG cash-flow chart (stdlib-generated) ────────────────────────────────────

def svg_cashflow(cashflow: list[dict], width: int = 640, height: int = 260) -> str:
    """Grouped bar chart: money-in (green) vs money-out (red) per month."""
    months = cashflow[-12:]
    if not months:
        return "<p class='muted'>No cash-flow data yet.</p>"

    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    peak = max((max(m["in"], m["out"]) for m in months), default=0.0) or 1.0

    def y(value: float) -> float:
        return pad_t + plot_h - (value / peak) * plot_h

    group_w = plot_w / len(months)
    bar_w = min(group_w / 2.6, 26)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="Monthly money in versus money out">',
        f'<line x1="{pad_l}" y1="{pad_t+plot_h}" x2="{width-pad_r}" '
        f'y2="{pad_t+plot_h}" stroke="currentColor" opacity="0.4"/>',
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+plot_h}" '
        'stroke="currentColor" opacity="0.4"/>',
    ]
    # y-axis ticks
    for frac in (0.0, 0.5, 1.0):
        yv = y(peak * frac)
        parts.append(
            f'<text x="{pad_l-6}" y="{yv+4:.1f}" font-size="10" '
            f'text-anchor="end" fill="currentColor" opacity="0.7">'
            f'${peak*frac:,.0f}</text>'
        )
    for i, m in enumerate(months):
        cx = pad_l + i * group_w + group_w / 2
        x_in = cx - bar_w - 1
        x_out = cx + 1
        y_in, y_out = y(m["in"]), y(m["out"])
        parts.append(
            f'<rect x="{x_in:.1f}" y="{y_in:.1f}" width="{bar_w:.1f}" '
            f'height="{pad_t+plot_h-y_in:.1f}" fill="#2e9e5b">'
            f'<title>{escape(m["month"])} in ${m["in"]:,.2f}</title></rect>'
        )
        parts.append(
            f'<rect x="{x_out:.1f}" y="{y_out:.1f}" width="{bar_w:.1f}" '
            f'height="{pad_t+plot_h-y_out:.1f}" fill="#c94f4f">'
            f'<title>{escape(m["month"])} out ${m["out"]:,.2f}</title></rect>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{height-pad_b+16}" font-size="10" '
            f'text-anchor="middle" fill="currentColor" opacity="0.8">'
            f'{escape(m["month"][2:])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ── HTML rendering ────────────────────────────────────────────────────────────

def _fmt_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _accounts_html(data: dict) -> str:
    rows = [
        f"<tr><td>{escape(str(a.get('name', '')))}</td>"
        f"<td class='muted'>{escape(str(a.get('type', '')))}</td>"
        f"<td class='num {'pos' if (a.get('balance') or 0) >= 0 else 'neg'}'>"
        f"{_fmt_money(a.get('balance') or 0.0)}</td></tr>"
        for a in data["accounts"]
    ]
    if not rows:
        rows = ["<tr><td colspan='3' class='muted'>No accounts yet.</td></tr>"]
    return (
        "<table class='accounts'><thead><tr><th>Account</th><th>Type</th>"
        "<th class='num'>Balance</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def _transactions_html(data: dict) -> str:
    rows = []
    for tx in data["transactions"]:
        amt = tx.get("amount") or 0.0
        cls = "pos" if amt >= 0 else "neg"
        rows.append(
            "<tr>"
            f"<td>{escape(str(tx.get('date', '')))}</td>"
            f"<td>{escape(str(tx.get('account_name') or '—'))}</td>"
            f"<td>{escape(str(tx.get('description', '')))}</td>"
            f"<td class='muted'>{escape(str(tx.get('category') or 'Other'))}</td>"
            f"<td class='num {cls}'>{_fmt_money(amt)}</td>"
            "</tr>"
        )
    if not rows:
        rows = ["<tr><td colspan='5' class='muted'>No transactions yet.</td></tr>"]
    return (
        "<table class='tx'><thead><tr><th>Date</th><th>Account</th>"
        "<th>Description</th><th>Category</th><th class='num'>Amount</th></tr>"
        "</thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _budget_html(data: dict) -> str:
    rows = []
    for cat, v in sorted(data["budget"].items()):
        budget = v.get("budget")
        if not budget:
            continue
        pct = v.get("pct", 0.0)
        spent = v.get("spent", 0.0)
        cls = "ok" if pct < 70 else "warn" if pct < 90 else "over"
        width = min(pct, 100)
        rows.append(
            "<div class='bud-row'>"
            f"<div class='bud-head'><span>{escape(cat)}</span>"
            f"<span class='muted'>{_fmt_money(spent)} / {_fmt_money(budget)} "
            f"({pct:.0f}%)</span></div>"
            f"<div class='bar'><div class='fill {cls}' style='width:{width:.0f}%'>"
            "</div></div></div>"
        )
    if not rows:
        return "<p class='muted'>No budget spending this month.</p>"
    return "".join(rows)


def _subscriptions_html(data: dict) -> str:
    subs = data["subscriptions"]
    if not subs:
        return "<p class='muted'>No recurring subscriptions detected.</p>"
    annual_total = sum(s["annualized"] for s in subs)
    rows = []
    for s in subs:
        if s["amount"] is not None:
            amount = _fmt_money(s["amount"])
        else:
            lo, hi = s["amount_range"]
            amount = f"{_fmt_money(lo)}–{_fmt_money(hi)}"
        status_cls = "over" if s["status"] == "possibly_cancelled" else "ok"
        status_label = "possibly cancelled" if s["status"] == "possibly_cancelled" else "active"
        rows.append(
            "<tr>"
            f"<td>{escape(s['normalized_merchant'])}</td>"
            f"<td class='muted'>{escape(s['cadence'])}</td>"
            f"<td class='num'>{amount}</td>"
            f"<td>{escape(s['next_expected'])}</td>"
            f"<td class='num'>{_fmt_money(s['monthly_equivalent'])}</td>"
            f"<td class='num'>{_fmt_money(s['annualized'])}</td>"
            f"<td class='num'>{s['confidence']*100:.0f}%</td>"
            f"<td class='status {status_cls}'>{status_label}</td>"
            "</tr>"
        )
    header = (
        f"<p class='headline'>You're committed to <b>{_fmt_money(annual_total)}"
        "/yr</b> in recurring charges.</p>"
    )
    return (
        header
        + "<table class='subs'><thead><tr><th>Merchant</th><th>Cadence</th>"
        "<th class='num'>Amount</th><th>Next due</th><th class='num'>Monthly</th>"
        "<th class='num'>Annual</th><th class='num'>Conf.</th><th>Status</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


_STYLE = """
:root{--fg:#23252b;--bg:#faf8f3;--card:#fff;--muted:#7a7d85;--line:#e4e0d6;
--pos:#2e7d46;--neg:#b3402f;--accent:#3b6ea5}
@media(prefers-color-scheme:dark){:root{--fg:#e6e3da;--bg:#1a1c20;--card:#24272d;
--muted:#9a9da5;--line:#33373f;--pos:#5fbf82;--neg:#e07d6d;--accent:#7fa8d6}}
*{box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
color:var(--fg);background:var(--bg);margin:0;padding:1.5rem;line-height:1.45}
.wrap{max-width:64rem;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .25rem}
h2{font-size:1.05rem;margin:0 0 .75rem;color:var(--accent)}
.sub{color:var(--muted);margin:0 0 1.5rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:1.1rem 1.25rem;margin-bottom:1.25rem;overflow-x:auto}
.total{font-size:2rem;font-weight:700}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:.35rem .5rem;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--muted);font-size:.78rem;text-transform:uppercase;
letter-spacing:.03em}
.num{text-align:right;font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.bud-row{margin-bottom:.7rem}
.bud-head{display:flex;justify-content:space-between;font-size:.85rem;
margin-bottom:.2rem}
.bar{height:9px;background:var(--line);border-radius:5px;overflow:hidden}
.fill{height:100%;border-radius:5px}
.fill.ok{background:var(--pos)}.fill.warn{background:#c99a2e}
.fill.over{background:var(--neg)}
.status{font-size:.8rem}.status.ok{color:var(--pos)}.status.over{color:var(--neg)}
.headline{margin:0 0 .75rem;font-size:.95rem}
.tx-scroll{max-height:26rem;overflow-y:auto}
footer{color:var(--muted);font-size:.8rem;text-align:center;margin-top:1rem}
"""


def page(db: LedgerDB, today: date) -> str:
    data = _collect(db, today)
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Private Ledger — mirror</title>"
        f"<style>{_STYLE}</style>"
        "<div class='wrap'>"
        "<h1>Private Ledger</h1>"
        f"<p class='sub'>Local mirror · {escape(data['today'])} · read-only · &Delta;&Sigma;=42</p>"
        "<div class='card'><h2>Balance</h2>"
        f"<div class='total {'pos' if data['total_balance'] >= 0 else 'neg'}'>"
        f"{_fmt_money(data['total_balance'])}</div>"
        f"{_accounts_html(data)}</div>"
        "<div class='card'><h2>Cash flow</h2>"
        f"{svg_cashflow(data['cashflow'])}</div>"
        "<div class='card'><h2>Budget</h2>"
        f"{_budget_html(data)}</div>"
        "<div class='card'><h2>Subscriptions</h2>"
        f"{_subscriptions_html(data)}</div>"
        "<div class='card'><h2>Transactions</h2>"
        f"<div class='tx-scroll'>{_transactions_html(data)}</div></div>"
        "<footer>Private Ledger — a mirror, not a service. No cloud, no egress.</footer>"
        "</div>"
    )


# ── Pure router ───────────────────────────────────────────────────────────────

def handle(method: str, path: str, db: LedgerDB, today: date) -> tuple[int, str, str]:
    """The entire routing table. Pure — no socket required. Read-only."""
    if method != "GET":
        return 405, _HTML, "method not allowed"
    if path == "/":
        return 200, _HTML, page(db, today)
    if path == "/data.json":
        return 200, _JSON, json.dumps(_collect(db, today), default=str)
    if path == "/subscriptions.json":
        transactions = _rows_to_dicts(db.get_transactions(limit=500))
        subs = subscriptions.detect_subscriptions(transactions, today)
        return 200, _JSON, json.dumps(subs, default=str)
    return 404, _HTML, "not found"


# ── http.server adapter (127.0.0.1 only) ──────────────────────────────────────

def serve(db: LedgerDB | None = None, host: str = "127.0.0.1",
          port: int = PORT, today: date | None = None) -> None:
    if today is None:
        today = date.today()
    if db is None:
        from . import pl_paths
        from .schema import init_ledger

        db_path = str(pl_paths.db_path())
        init_ledger(db_path)
        db = LedgerDB(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — http.server API
            status, ctype, body = handle("GET", self.path.split("?")[0], db, today)
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802 — read-only mirror
            status, ctype, body = handle("POST", self.path.split("?")[0], db, today)
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # quiet
            pass

    print(f"Private Ledger mirror: http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()
