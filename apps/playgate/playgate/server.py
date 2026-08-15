"""Loopback host for the kid and parent UIs.

The only module in this app that imports anything network-shaped, and it binds
127.0.0.1. `tests/test_no_egress.py` scans every other module for network
imports and scans this one for *outbound* clients — the distinction being that
serving a socket the browser on this machine connects to is not egress, and
opening one to somewhere else is.

Nothing here phones home. There is no telemetry, no update check, and no
report of what a child asked for leaving the machine. Routing a request to the
parent in the next room is the entire mechanism; receiving a copy of it
somewhere else is not part of it.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import catalog as catalog_mod
from . import install as install_mod
from .disposition import GRANTED, DispositionError, Log
from .interruption import InterruptionError

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8424
DEFAULT_HOST = "127.0.0.1"

STATIC_ROOTS = {"/kid/": APP_ROOT / "kid", "/parent/": APP_ROOT / "parent"}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "playgate"

    # Injected by serve()
    apps: list = []
    log: Log = None            # type: ignore[assignment]
    #: Where installable APKs live. Deliberately not defaulted to APP_ROOT — an
    #: unconfigured host must refuse to install, not quietly search its own
    #: install directory.
    apk_root: "Path | None" = None

    # -- plumbing ----------------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # This UI loads no third-party anything and must not be able to start.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DispositionError(f"body is not JSON: {exc}") from exc

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        """Quiet by default. Request lines would be a second, unreasoned record
        of what a child asked for, sitting outside the disposition log."""

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        if route in ("/", "/kid", "/parent"):
            target = "/kid/" if route in ("/", "/kid") else "/parent/"
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return

        if route == "/api/catalog":
            query = parse_qs(parsed.query).get("q", [None])[0]
            found = catalog_mod.search(self.apps, query)
            self._json(200, {"apps": [app.view() for app in found]})
            return

        if route == "/api/requests":
            params = parse_qs(parsed.query)
            subject = params.get("subject", [None])[0]
            if subject is not None:
                # The child's own view. Checked against the roster for the same
                # reason every other subject is: an id nobody was started with
                # is not a person this host knows about, and answering for it
                # would invent one.
                if subject not in self.log.roster:
                    self._error(400, f"subject {subject!r} is not on the roster")
                    return
                self._json(200, {"requests": self.log.for_subject(subject)})
                return
            view = params.get("view", ["open"])[0]
            if view != "open":
                self._error(400, f"unknown view {view!r}")
                return
            self._json(200, {"requests": self.log.open_requests()})
            return

        if route == "/api/roster":
            self._json(200, {"subjects": list(self.log.roster)})
            return

        self._static(route)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            body = self._body()
            if route == "/api/requests":
                self._create_request(body)
            elif route.startswith("/api/requests/") and route.endswith("/answer"):
                self._answer(route.split("/")[3], body)
            else:
                self._error(404, f"no route {route}")
        except (DispositionError, InterruptionError) as exc:
            self._error(400, str(exc))

    def _create_request(self, body: dict) -> None:
        app_id = body.get("app_id", "")
        if catalog_mod.by_id(self.apps, app_id) is None:
            self._error(400, f"no app {app_id!r} in this catalog")
            return
        row = self.log.request(
            subject_id=body.get("subject_id", ""),
            app_id=app_id,
            asked_by=body.get("asked_by", ""),
            within_hours=int(body.get("within_hours", 48)),
        )
        self._json(201, {"request": row})

    def _answer(self, request_id: str, body: dict) -> None:
        state = self.log.current(request_id)
        if state is None:
            self._error(404, f"no such request {request_id!r}")
            return
        app = catalog_mod.by_id(self.apps, state["app_id"])
        granted = bool(body.get("granted"))

        answered = self.log.answer(
            request_id=request_id,
            granted=granted,
            by=body.get("by", ""),
            reason=body.get("reason", ""),
            interruption=app.interruption.effective(app.version) if app else None,
        )

        if answered["disposition"] != GRANTED:
            self._json(200, {"request": self.log.current(request_id)})
            return

        # The gate closes here. Telling the parent to go and run an install
        # command in a terminal would leave a to-do list with a reason field
        # where a gate is supposed to be.
        result = self._install(app)
        self.log.record_install(request_id, result.ok, result.detail)
        self._json(200, {
            "request": self.log.current(request_id),
            "install": {"ok": result.ok, "detail": result.detail},
        })

    def _install(self, app) -> install_mod.Result:
        if app is None or not app.apk_path:
            return install_mod.Result(False, "catalog entry has no apk_path")
        if self.apk_root is None:
            return install_mod.Result(
                False, "no apk root configured; start with --apk-root or set "
                       "PLAYGATE_APK_DIR"
            )
        return install_mod.perform(self.apk_root / app.apk_path, app.sha256 or "")

    def _static(self, route: str) -> None:
        for prefix, root in STATIC_ROOTS.items():
            if not route.startswith(prefix):
                continue
            relative = route[len(prefix):] or "index.html"
            target = (root / relative).resolve()
            if not target.is_file() or root.resolve() not in target.parents:
                break
            content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            self._send(200, target.read_bytes(), content_type)
            return
        self._error(404, "not found")


def build_handler(apps, log: Log, apk_root: "Path | None") -> type:
    return type("BoundHandler", (Handler,), {
        "apps": apps, "log": log, "apk_root": apk_root,
    })


def serve(apps, log: Log, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          apk_root: "Path | None" = None) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError(
            f"refusing to bind {host!r}: this host serves a child's request "
            "queue and a parent's decisions, and is loopback-only by design"
        )
    return ThreadingHTTPServer((host, port), build_handler(apps, log, apk_root))
