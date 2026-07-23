"""
web.py — the on-device mirror: the reliability diagram. b17: OAKOF

Pattern: utety/web/server.py — routing is a pure function, handle(method,
path) -> (status, content_type, body), so the whole surface is unit-testable
without a socket. serve() adapts it to http.server for real use. Localhost
only by default; this is a mirror, not a service.

Usage:
  python3 web.py           # http://127.0.0.1:8437
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

import calibration
import office_db as db

_HTML = "text/html; charset=utf-8"
_JSON = "application/json"
PORT = 8437


def svg_reliability(bins: list[dict], size: int = 440) -> str:
    """Stated confidence (x, 50–100%) vs actual hit rate (y, 0–100%).
    The diagonal is perfect calibration; dots below it are overconfidence.
    Dot area scales with n."""
    pad = 48
    span = size - 2 * pad

    def x(conf: float) -> float:
        return pad + (conf - 0.5) / 0.5 * span

    def y(rate: float) -> float:
        return size - pad - rate * span

    parts = [
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Reliability diagram">',
        f'<rect width="{size}" height="{size}" fill="none"/>',
        # axes
        f'<line x1="{pad}" y1="{size-pad}" x2="{size-pad}" y2="{size-pad}" stroke="currentColor"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{size-pad}" stroke="currentColor"/>',
        # the diagonal of honesty: y = x over the stated range
        f'<line x1="{x(0.5)}" y1="{y(0.5)}" x2="{x(1.0)}" y2="{y(1.0)}" '
        'stroke="currentColor" stroke-dasharray="4 4" opacity="0.5"/>',
    ]
    for frac in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        parts.append(
            f'<text x="{x(frac)}" y="{size-pad+18}" font-size="11" '
            f'text-anchor="middle" fill="currentColor">{frac:.0%}</text>'
        )
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        parts.append(
            f'<text x="{pad-8}" y="{y(frac)+4}" font-size="11" '
            f'text-anchor="end" fill="currentColor">{frac:.0%}</text>'
        )
    for b in bins:
        if not b["n"]:
            continue
        r = 4 + (b["n"] ** 0.5) * 2
        parts.append(
            f'<circle cx="{x(b["mean_confidence"])}" cy="{y(b["hit_rate"])}" r="{r:.1f}" '
            f'fill="currentColor" opacity="0.65"><title>'
            f'{b["lo"]:.0%}–{b["hi"]:.0%}: said {b["mean_confidence"]:.0%}, '
            f'hit {b["hit_rate"]:.0%} (n={b["n"]})</title></circle>'
        )
    parts.append(
        f'<text x="{size/2}" y="{size-8}" font-size="12" text-anchor="middle" '
        'fill="currentColor">stated confidence</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def page() -> str:
    pairs = db.resolved_pairs()
    s = calibration.summary(pairs)
    b = calibration.bins(pairs)
    if s["n"]:
        verdict = (
            f"overconfident by {s['overconfidence']:+.0%}" if s["overconfidence"] > 0.02
            else f"underconfident by {s['overconfidence']:+.0%}" if s["overconfidence"] < -0.02
            else "well calibrated"
        )
        header = (
            f"<p><b>{s['n']}</b> graded · Brier <b>{s['brier']:.3f}</b> · "
            f"you say <b>{s['mean_confidence']:.0%}</b>, you deliver "
            f"<b>{s['hit_rate']:.0%}</b> — <b>{verdict}</b></p>"
        )
        diagram = svg_reliability(b)
    else:
        header = "<p>No graded predictions yet. The curve appears when the world weighs in.</p>"
        diagram = ""
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Oakenscroll's Office — the scorecard</title>"
        "<style>body{font-family:Georgia,serif;max-width:40rem;margin:2rem auto;"
        "padding:0 1rem;color:#2b2b2b;background:#faf7f0}"
        "@media(prefers-color-scheme:dark){body{color:#e8e4da;background:#1e1c18}}"
        "h1{font-size:1.4rem}</style>"
        "<h1>Oakenscroll&rsquo;s Office</h1>"
        "<p><i>Where certainty gets graded. &Delta;&Sigma;=42</i></p>"
        + header + diagram
    )


def handle(method: str, path: str) -> tuple[int, str, str]:
    """The entire routing table. Pure — no socket required."""
    if method != "GET":
        return 405, _HTML, "method not allowed"
    if path == "/":
        return 200, _HTML, page()
    if path == "/data.json":
        pairs = db.resolved_pairs()
        return 200, _JSON, json.dumps({
            "summary": calibration.summary(pairs),
            "bins": calibration.bins(pairs),
        })
    if path == "/ledger.json":
        return 200, _JSON, json.dumps(db.ledger())  # includes citation evidence
    return 404, _HTML, "not found"


def serve(port: int = PORT) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — http.server API
            status, ctype, body = handle("GET", self.path.split("?")[0])
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # quiet
            pass

    print(f"Oakenscroll's Office mirror: http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    import sys
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
