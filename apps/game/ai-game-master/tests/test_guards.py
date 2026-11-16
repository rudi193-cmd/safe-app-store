"""ai-game-master — the guards, run in CI.

Every claim this blueprint makes is a mechanism with a test that tries the
forbidden act and asserts the refusal. A guard that cannot be shown to fail has
not been shown to work.

Run from the app root: `python -m pytest tests/ -q` (the store's app-tests
matrix does exactly this).
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(APP, "bootstrap", "verify_ledger.py")
POC = os.path.join(APP, "docs", "poc_vander_room.py")
SCHEMA = os.path.join(APP, "schema")


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    for f in ("01_ledger", "02_canon", "03_entities", "04_rulings",
              "05_corpus.reference"):
        con.executescript(open(os.path.join(SCHEMA, f + ".sql")).read())
    return con, path


# ── the tamper-evidence chain ────────────────────────────────────────────────
def test_self_test_passes():
    """verify_ledger --self-test builds a clean chain, tampers a row, and the
    tamper IS refused. Exit 0 means the whole demonstration held."""
    r = subprocess.run([sys.executable, VERIFY, "--self-test"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tampered row refused" in r.stdout


def test_poc_carries_the_game():
    """The Vander boss room replays through the real schema and the chain +
    canon guard verify at the end."""
    r = subprocess.run([sys.executable, POC], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "EXHIBIT OK" in r.stdout


# ── the covenant CHECKs bite at write time ───────────────────────────────────
def test_sealed_canon_needs_a_human():
    con, path = _fresh_db()
    try:
        try:
            con.execute("INSERT INTO canon(ts,fact,status) VALUES('t','x','SEALED')")
            con.commit()
            assert False, "a SEALED row with no sealer must be refused"
        except sqlite3.IntegrityError:
            pass
    finally:
        con.close(); os.unlink(path)


def test_a_proposal_may_not_carry_a_seal():
    con, path = _fresh_db()
    try:
        try:
            con.execute("INSERT INTO canon(ts,fact,status,sealed_by) "
                        "VALUES('t','x','PENDING','Sean')")
            con.commit()
            assert False, "a PENDING row that names a sealer must be refused"
        except sqlite3.IntegrityError:
            pass
    finally:
        con.close(); os.unlink(path)


def test_ccby_row_needs_attribution():
    con, path = _fresh_db()
    try:
        try:
            con.execute("INSERT INTO corpus(source,licence,tier,text) "
                        "VALUES('SRD-5.1','CC-BY-4.0','reuse','rules')")
            con.commit()
            assert False, "a CC-BY corpus row with no attribution must be refused"
        except sqlite3.IntegrityError:
            pass
    finally:
        con.close(); os.unlink(path)


# ── the covenant guard refuses a machine seal on read ────────────────────────
def test_machine_sealed_canon_is_refused():
    con, path = _fresh_db()
    try:
        # passes the CHECK (name is non-empty) but is not a person
        con.execute("INSERT INTO canon(ts,fact,status,sealed_by) "
                    "VALUES('t','the button is bait','SEALED','claude')")
        con.commit(); con.close()
        r = subprocess.run([sys.executable, VERIFY, path, "--canon"],
                           capture_output=True, text=True)
        assert r.returncode == 1, r.stdout
        assert "not a person" in r.stdout
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_clean_canon_passes_the_guard():
    con, path = _fresh_db()
    try:
        con.execute("INSERT INTO canon(ts,fact,status,proposed_by,sealed_by,sealed_at) "
                    "VALUES('t','Prince freed','SEALED','machine','DM-Sean','t')")
        con.commit(); con.close()
        r = subprocess.run([sys.executable, VERIFY, path, "--canon"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout
    finally:
        if os.path.exists(path):
            os.unlink(path)
