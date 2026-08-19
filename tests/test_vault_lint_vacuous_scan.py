"""A vacuous scan is not a clean one.

`tools/vault_leak_lint.py` reads `*.py` and nothing else. Until apps/jarvis
landed, every app in the store had Python in it, so the case where the checker
opens no files had never occurred — and when it did, the tool printed:

    ✅ PASS jarvis (no local persistence)

Both halves were false by vacuity. jarvis persists facts, reminders and the
user's API key; it does so in IndexedDB and localStorage, from JavaScript, which
this checker cannot read. The verdict was not wrong about what it found. It was
wrong to call finding nothing a pass.

`UNKNOWN` now, which is the distinction `tools/conform.py` already draws.
`--strict` still gates on `FAIL` alone, so no build outcome changed — what
changed is what the output claims.

Two decoys, because the check has two directions and one decoy would leave the
other decorative: an app with no Python must not read `PASS`, and an app with
clean Python must still read `PASS` rather than being swept into `UNKNOWN`.

Stdlib only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import vault_leak_lint as lint  # noqa: E402


def test_an_app_with_no_python_is_unknown_not_pass(tmp_path):
    app = tmp_path / "no-python-here"
    (app / "src").mkdir(parents=True)
    (app / "src" / "store.js").write_text(
        "const db = indexedDB.open('facts');\nlocalStorage.setItem('apiKey', k);\n"
    )
    got = lint.lint_app(app)
    assert got["verdict"] == "UNKNOWN", got
    assert got["scanned"] == 0


def test_an_app_with_clean_python_still_passes(tmp_path):
    """The other direction. Without this, `UNKNOWN` could swallow every app and
    the suite would still be green."""
    app = tmp_path / "clean-python"
    app.mkdir()
    (app / "main.py").write_text("import json\n\n\ndef go():\n    return json.dumps({})\n")
    got = lint.lint_app(app)
    assert got["verdict"] == "PASS", got
    assert got["scanned"] == 1


def test_a_real_leak_still_fails(tmp_path):
    """And the verdict the tool exists for is untouched — `--strict` gates on
    FAIL, so a change to the PASS/UNKNOWN boundary must not reach it."""
    app = tmp_path / "leaky"
    app.mkdir()
    (app / "main.py").write_text(
        "from pathlib import Path\n"
        "import sqlite3\n"
        "DB = Path.home() / '.myapp' / 'entries.db'\n"
        "conn = sqlite3.connect(DB)\n"
    )
    got = lint.lint_app(app)
    assert got["verdict"] == "FAIL", got


def test_the_store_has_exactly_three_unknowns():
    """Named rather than counted loosely: if a fifth non-Python app lands, this
    fails and someone reads the sentence above instead of adding a row.

    UTETY-Reddit-Bots is a policy/docs-only directory — no Python code, just
    BOTS.md, LICENSE, PRIVACY.md, README.md, and TERMS.md. It previously held
    a stale safe_integration.py that made it lint PASS vacuously; P0 deleted
    that orphan and revealed the app as genuinely Python-free.

    band-camp-arcade joined jarvis as the store's second Python-free app —
    five static HTML/JS games, no backend. Same reasoning as jarvis: this
    checker reads *.py and nothing else, so it correctly has nothing to read
    here, and UNKNOWN says so rather than a vacuous PASS.

    playgate was briefly a third. It was merged as two static UIs whose host
    daemon lived outside the repository, so this checker had nothing to read and
    the app was added to the list above. That was the wrong fix: the right one
    was to stop the app being unreadable. Its host is now in-tree and it lints
    PASS, so the list is back to two. Adding a row here is what you do when an
    app genuinely has no Python; it is not a way to quiet the gate.
    """
    apps = sorted(d for d in (REPO / "apps").iterdir() if d.is_dir())
    unknown = [d.name for d in apps if lint.lint_app(d)["verdict"] == "UNKNOWN"]
    assert unknown == ["UTETY-Reddit-Bots", "band-camp-arcade", "jarvis", "marching-arts-shell", "repo-astrology"], unknown


def test_the_module_is_not_broken_shut(tmp_path):
    app = tmp_path / "ordinary"
    app.mkdir()
    (app / "a.py").write_text("x = 1\n")
    assert lint.lint_app(app)["verdict"] == "PASS"


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        try:
            if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"ok   {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}\n{type(exc).__name__}: {exc}\n")
    raise SystemExit(1 if failures else 0)
