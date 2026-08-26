"""Operator drive — the scratchpad probe recast as a single-function pytest.

Same 26 checks the lab version ran (sections A–G). If any assertion trips
here, the build is not ready for `make run`, let alone promotion.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT / "src"))

pytest.importorskip("nestor", reason="fleet-glue needs nestor-meaning installed")
pytest.importorskip("jeles",  reason="fleet-glue needs jeles installed")
pytest.importorskip("willow_mcp", reason="fleet-glue needs willow-mcp installed")


def _bind(lab: Path):
    from fleet_glue import configure_lab, install
    configure_lab(lab)
    # seed the Nestor demo store the CLI ships (its rows are what tier-1 hits)
    subprocess.run(
        ["nestor", "--db", os.environ["NESTOR_DB"],
         "--ledger", os.environ["NESTOR_LEDGER"],
         "demo", "--seed", "default"],
        check=True, capture_output=True,
    )
    from nestor.sqlite_store import SqliteStore
    from nestor.storage import set_store
    from nestor.cascade import set_ledger_path
    set_ledger_path(os.environ["NESTOR_LEDGER"])
    set_store(SqliteStore(os.environ["NESTOR_DB"]))
    install(seed_jeles_demo=True)


def test_operator_drive(tmp_path):
    lab = tmp_path / "lab"
    if lab.exists():
        shutil.rmtree(lab)
    _bind(lab)

    from fleet_glue import (
        log_gap, list_all_gaps,
        corroborate_to_draft, promote_gap_to_jeles, promote_gap_to_nestor_draft,
        advisory_ratify, conflict_scan, triage_summary,
    )
    from nestor.cascade import translate_segment, get_tier15_recognizer
    from nestor.storage import get_store
    from nestor.matcher import StringMatcher
    from nestor import cascade, memory
    from jeles import corpus as jc

    store, mtch = get_store(), StringMatcher()

    # --- A. day-in-life ---
    gaps = [log_gap(q, topic="ops") for q in [
        "What is the current freeze window?",
        "What is the on-call rotation for August?",
        "Where do we file a post-mortem?",
    ]]
    assert all(g["willow_gap_id"] and g["jeles_gap_id"] for g in gaps), "dual-write ids"

    d = advisory_ratify(
        claim_id="ops:freeze-window", proposer_id="rita",
        current_tier="contested", target_tier="frontier",
        witnesses=[{"agent_id": "rita", "base_model": "human", "independence_evidence": "policy"}],
    )
    assert d["allowed"] is False, "lone witness must be denied"

    draft = promote_gap_to_nestor_draft(
        "What is the current freeze window?",
        "Fridays 16:00 UTC through Monday 09:00 UTC.",
        "policy", "text",
        sources=["https://intranet/ops/freeze-2026"],
    )
    assert draft["status"] == "draft"

    d2 = advisory_ratify(
        claim_id="ops:oncall-aug", proposer_id="claude-code",
        current_tier="contested", target_tier="frontier",
        witnesses=[
            {"agent_id": "rita",           "base_model": "human", "independence_evidence": "schedule"},
            {"agent_id": "pagerduty-bot",  "base_model": "pd-api","independence_evidence": "api"},
        ],
        ledger_evidence_ref="nestor:ledger:head",
    )
    assert d2["allowed"] is True

    pr = promote_gap_to_jeles(
        "What is the on-call rotation for August?",
        "Marcus (weeks 1-2), Priya (3-4).",
        sources=["https://pd.example/oncall/aug2026"],
        topic="ops", verified_by="rita",
        willow_gap_id=gaps[1]["willow_gap_id"],
    )
    match = [g for g in list_all_gaps(topic="ops")["willow"] if g.get("_id") == gaps[1]["willow_gap_id"]]
    assert match and match[0]["status"] == "promoted" and match[0]["promoted_to"] == pr["nugget_id"]

    # --- B. adversarial ---
    with pytest.raises(ValueError, match="expected one of"):
        advisory_ratify("x", "y", target_tier="bogus")

    with pytest.raises((KeyError, TypeError)):
        advisory_ratify("x", "y", witnesses=[{"agent_id": "solo"}])  # no base_model

    with pytest.raises(TypeError):
        advisory_ratify("x", "y", witnesses=["just-a-string"])

    # empty question must not crash the dual-write
    ge = log_gap("", topic="edge")
    assert isinstance(ge["jeles"], dict) and isinstance(ge["willow"], dict)

    # bogus willow gap id: nugget still written, resolve reports error, marked=False
    pr_bad = promote_gap_to_jeles("boom", "answer", sources=[], willow_gap_id="deadbeefdead")
    assert pr_bad["nugget_id"] and pr_bad["gap_marked_promoted"] is False

    # --- C. idempotency ---
    from fleet_glue import install as fg_install
    first = get_tier15_recognizer()
    fg_install()
    assert first is get_tier15_recognizer(), "install() twice must not double-register"

    before = list(jc.list_nuggets(limit=200) or [])
    jc.put_nugget(
        nugget_id="demo-paris",
        question="What is the capital of France?", answer="Paris",
        sources=["https://en.wikipedia.org/wiki/Paris"],
        verified_by="demo-curator", verification_kind="human",
        tags=["domain:geo->desc"],
    )
    after = list(jc.list_nuggets(limit=200) or [])
    assert len(before) == len(after), "put_nugget with same id must update, not duplicate"

    p1 = translate_segment("42", "number", "meaning", store=store, matcher=mtch)
    p2 = translate_segment("42", "number", "meaning", store=store, matcher=mtch)
    con = sqlite3.connect(os.environ["NESTOR_DB"])
    n = con.execute(
        "SELECT COUNT(*) FROM tm_pairs WHERE source_norm='42' AND source_lang='number' "
        "AND target_lang='meaning' AND status='draft' AND (superseded_by='' OR superseded_by IS NULL)"
    ).fetchone()[0]
    con.close()
    assert p1.meta.get("pair_id") == p2.meta.get("pair_id") and n == 1

    # --- D. rejection wall ---
    memory.reject_pair(p1.meta["pair_id"], verifier="rita", reason="test:reject-wall")
    p3 = translate_segment("42", "number", "meaning", store=store, matcher=mtch)
    assert p3.engine != "established", "rejected pair must not re-establish"
    p4 = translate_segment("paris", "geo", "desc", store=store, matcher=mtch)
    assert p4.engine == "established", "unrelated established still recognized"

    # --- E. conflict_scan.apply ---
    n_before = len(list(jc.list_nuggets(limit=500) or []))
    g_before = len(list(jc.list_gaps(limit=500) or []))
    cs = conflict_scan("HTTP 429 means Too Many Requests", apply=True)
    grew = (len(list(jc.list_nuggets(limit=500) or [])) - n_before) + \
           (len(list(jc.list_gaps(limit=500) or [])) - g_before)
    assert grew >= 1, "conflict_scan.apply must write at least one row"

    # --- F. ledger + triage ---
    r = subprocess.run(
        ["nestor", "--db", os.environ["NESTOR_DB"], "--ledger", os.environ["NESTOR_LEDGER"], "ledger", "verify"],
        capture_output=True, text=True,
    )
    assert "intact" in (r.stdout + r.stderr).lower()

    c = triage_summary()["counts"]
    assert (c["seal"] >= 4 and c["known"] >= 2 and c["reject"] >= 1
            and c["gaps_willow_open"] >= 1 and c["gaps_jeles"] >= 1), c

    # --- G. cross-session persistence ---
    child_env = {k: v for k, v in os.environ.items() if k != "NESTOR_SEAL_KEY"}
    child = subprocess.run(
        [sys.executable, "-c", (
            f"import sys, os, json\n"
            f"sys.path.insert(0, {str(APP_ROOT / 'src')!r})\n"
            f"from fleet_glue import configure_lab, install\n"
            f"cfg = configure_lab({str(lab)!r})\n"
            f"r = install()\n"
            f"from nestor.sqlite_store import SqliteStore\n"
            f"from nestor.storage import set_store\n"
            f"from nestor.cascade import set_ledger_path, translate_segment, get_tier15_recognizer\n"
            f"from nestor.matcher import StringMatcher\n"
            f"set_ledger_path(os.environ['NESTOR_LEDGER'])\n"
            f"s = SqliteStore(os.environ['NESTOR_DB']); set_store(s)\n"
            f"import sqlite3\n"
            f"con = sqlite3.connect(os.environ['NESTOR_DB'])\n"
            f"sealed = con.execute(\"SELECT COUNT(*) FROM tm_pairs WHERE status='sealed'\").fetchone()[0]\n"
            f"corr = con.execute(\"SELECT COUNT(*) FROM tm_pairs WHERE origin='corroborated-fleet-glue'\").fetchone()[0]\n"
            f"con.close()\n"
            f"p = translate_segment('42', 'number', 'meaning', store=s, matcher=StringMatcher())\n"
            f"p2 = translate_segment('paris', 'geo', 'desc', store=s, matcher=StringMatcher())\n"
            f"print(json.dumps({{\n"
            f"  'seal_key_source': cfg['NESTOR_SEAL_KEY']['source'],\n"
            f"  'wire': r['wire'],\n"
            f"  'tier15_wired': get_tier15_recognizer() is not None,\n"
            f"  'sealed_count': sealed,\n"
            f"  'corroborated_count': corr,\n"
            f"  'rejected_reask_engine': p.engine,\n"
            f"  'unrelated_established_engine': p2.engine,\n"
            f"}}))\n"
        )],
        capture_output=True, text=True, env=child_env,
    )
    assert child.returncode == 0, child.stderr
    out = json.loads(child.stdout.strip())
    assert out["seal_key_source"] == "seal.key", "child must read seal key from disk"
    assert out["tier15_wired"] is True
    assert out["sealed_count"] >= 4
    assert out["corroborated_count"] >= 1
    assert out["rejected_reask_engine"] != "established", "rejection wall must persist"
    assert out["unrelated_established_engine"] == "established"

    r2 = subprocess.run(
        ["nestor", "--db", os.environ["NESTOR_DB"], "--ledger", os.environ["NESTOR_LEDGER"], "ledger", "verify"],
        capture_output=True, text=True,
    )
    assert "intact" in (r2.stdout + r2.stderr).lower()
