"""
The chokepoint invariant, enforced.

Two grep-provable properties of the live app (gatefirst/ is a sealed
prototype with its own store; squirrel_db.py is the deprecated pre-L2
module kept for reference; tests may do surgical cleanup):

  1. No module outside db/ runs SQL against a PII table. Everything
     routes through the gated functions — which is what makes the SAP
     gate a gate instead of a suggestion.
  2. No module in the app opens an outside socket. Egress is links the
     user clicks; the only permitted urlopen target is localhost Ollama.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent

_EXCLUDED = {"tests", "gatefirst", "docs", ".pytest_cache", "__pycache__"}
_DB_DIR = APP / "db"
_DEPRECATED = {APP / "squirrel_db.py", APP / "backfill_oscar_mann.py"}

_PII_SQL = re.compile(
    r"\b(FROM|INTO|UPDATE|JOIN|DELETE\s+FROM)\s+(the_squirrel\.)?"
    r"(persons|fragments|relationships|person_lattice_cells|person_sources|"
    r"fragment_lattice_cells|tree_branches|events|media)\b",
    re.IGNORECASE)


def _app_files():
    for path in APP.rglob("*.py"):
        parts = set(path.relative_to(APP).parts)
        if parts & _EXCLUDED or path in _DEPRECATED:
            continue
        if _DB_DIR in path.parents:
            continue
        yield path


def test_no_pii_sql_outside_db():
    offenders = []
    for path in _app_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _PII_SQL.search(line) and not line.strip().startswith("#"):
                offenders.append(f"{path.relative_to(APP)}:{i}: {line.strip()[:80]}")
    assert not offenders, (
        "PII-table SQL outside db/ — route it through the gated functions:\n"
        + "\n".join(offenders))


def test_no_outbound_sockets():
    net = re.compile(r"urllib\.request\.urlopen|http\.client\.HTTPS?Connection\(|socket\.create_connection")
    offenders = []
    for path in _app_files():
        text = path.read_text(encoding="utf-8")
        if not net.search(text):
            continue
        # The one sanctioned destination: localhost Ollama.
        if "localhost:11434" in text or "OLLAMA_URL" in text:
            continue
        offenders.append(str(path.relative_to(APP)))
    assert not offenders, (
        "outbound network call outside the Ollama-localhost allowance:\n"
        + "\n".join(offenders))
