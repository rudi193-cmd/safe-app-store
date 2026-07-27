"""Drift-guard: no app re-derives the vault root inline (box audit A5).

The vault root — where the local SAFE vault box lives — is a security boundary:
it is the single decision of where every app's data is written. It was copied,
byte-identical, into nine ``*_paths.py`` resolvers plus a few stragglers
(njord/paths.py, ask-jeles/kb_search.py, nest-seed/app.py), each spelling the
default as ``Path.home() / ".willow" / "store"``. Nine+ copies of a boundary is
nine+ places for it to drift. It now lives once, in the ``vault_paths`` library;
apps import ``vault_root`` / ``app_dir`` / ``resolve`` from it.

This test fails if any live (non-archived, non-test) app file spells the inline
vault-root default again, so the boundary can't fork back into per-app copies.
Setting the ``WILLOW_STORE_ROOT`` env var (e.g. in tests) is fine — this only
flags re-deriving the default *location* (``.willow/store``) in app code.
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# The inline default vault location: ``.willow`` joined to ``store``, whether as
# a pathlib expression (``... / ".willow" / "store"`` — the *_paths.py /
# kb_search / nest-seed resolvers) or a string join (``os.path.join(
# expanduser("~"), ".willow", "store")`` — the safe_integration.py health-check
# shims). Both now derive from vault_paths instead. Only the vault_paths lib —
# under libs/, not apps/ — should spell the default location.
_INLINE_DEFAULT = re.compile(r"""\.willow['"]?\s*[/,]\s*['"]?store""")

_SKIP_PARTS = {"_archived", "__pycache__", ".git", "node_modules", ".venv",
               "venv", "tests", "test"}


def _live_app_py_files():
    for p in (_REPO / "apps").rglob("*.py"):
        if _SKIP_PARTS & set(p.parts):
            continue
        yield p


def test_no_app_rederives_the_vault_root_inline():
    offenders = []
    for p in _live_app_py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if _INLINE_DEFAULT.search(line):
                offenders.append(f"{p.relative_to(_REPO)}:{i}  {line.strip()}")
    assert not offenders, (
        "vault root re-derived inline (box audit A5) — import vault_root / "
        "app_dir / resolve from the shared vault_paths library instead:\n  "
        + "\n  ".join(sorted(offenders)))
