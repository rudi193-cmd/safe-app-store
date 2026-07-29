"""subject_consent.core — the fail-closed, stdlib-only guardian-consent engine.

Two properties are load-bearing and each has its own section below:

  1. **Fail-closed.** Exactly like willow_mcp.consent, anything we cannot read
     as a verified GRANTED denies: an absent store, an unparseable chain, a
     tampered chain, no record, a pending grant, a revocation — all `False`.
     Consent is never inferred; absence is not consent.

  2. **Egress-free / stdlib-only.** The core runs on a child's device (UTETY)
     and under corpus-lens's stdlib-only charter, so `core` must import nothing
     but the standard library — no willow_mcp runtime, no network stack. This
     mirrors UTETY's test_boundaries.py: the boundary is a test, not a comment.
"""
import ast
import json
import sys
from pathlib import Path

import pytest

from subject_consent import core
from subject_consent.core import (
    ChainTamperError,
    DeidentificationError,
    FileBackend,
    SubjectConsentError,
    deidentify,
    grant,
    permitted,
    read_disclosures,
    record_disclosure,
    revoke,
    verify_consent_chain,
)

OWNER = "operator"


# ── fail-closed: the gate denies on every path that isn't a verified GRANTED ──

def test_absent_store_denies(tmp_path):
    # nothing written yet — the file does not exist
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False


def test_unknown_scope_denies(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    assert permitted(tmp_path, "subj-1", "not_a_real_scope") is False


def test_no_record_for_pair_denies(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    # same subject, different scope → no grant for THIS pair
    assert permitted(tmp_path, "subj-1", "person_inference") is False
    # same scope, different subject
    assert permitted(tmp_path, "subj-2", "kb_promotion") is False


def test_grant_permits_only_its_pair(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    assert permitted(tmp_path, "subj-1", "kb_promotion") is True


def test_revoke_denies_from_then_on(tmp_path):
    grant(tmp_path, "subj-1", "person_inference", OWNER)
    assert permitted(tmp_path, "subj-1", "person_inference") is True
    revoke(tmp_path, "subj-1", "person_inference", OWNER)
    assert permitted(tmp_path, "subj-1", "person_inference") is False


def test_regrant_after_revoke_permits_again(tmp_path):
    # latest transition wins — the chain is a history, not a one-way latch
    grant(tmp_path, "subj-1", "local_only", OWNER)
    revoke(tmp_path, "subj-1", "local_only", OWNER)
    grant(tmp_path, "subj-1", "local_only", OWNER)
    assert permitted(tmp_path, "subj-1", "local_only") is True


def test_grant_rejects_unknown_scope(tmp_path):
    with pytest.raises(SubjectConsentError):
        grant(tmp_path, "subj-1", "telepathy", OWNER)


def test_grant_rejects_empty_grantor(tmp_path):
    with pytest.raises(SubjectConsentError):
        grant(tmp_path, "subj-1", "kb_promotion", "   ")


def test_grant_rejects_empty_subject(tmp_path):
    with pytest.raises(SubjectConsentError):
        grant(tmp_path, "  ", "kb_promotion", OWNER)


def test_owner_is_not_special_cased(tmp_path):
    # the core does not know who the owner is; owner==subject still needs a grant
    assert permitted(tmp_path, OWNER, "kb_promotion") is False
    grant(tmp_path, OWNER, "kb_promotion", OWNER)
    assert permitted(tmp_path, OWNER, "kb_promotion") is True


# ── tamper-evidence: an edited or truncated chain denies AND is detectable ────

def test_tampered_chain_denies_silently_at_gate(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    path = tmp_path / "consent.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    # flip the status in place without recomputing the hash
    tampered = rows[0].replace('"granted"', '"revoked"') if '"granted"' in rows[0] else rows[0]
    if tampered == rows[0]:
        tampered = rows[0].replace("granted", "grantedX")
    path.write_text(tampered + "\n", encoding="utf-8")
    # the gate never raises — it just denies
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False


def test_tampered_chain_raises_on_admin_verify(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    path = tmp_path / "consent.jsonl"
    row = path.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(row.replace("kb_promotion", "person_inference") + "\n", encoding="utf-8")
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)


def test_verify_absent_chain_is_not_tampered(tmp_path):
    # a store that was never written is clean, not broken
    verify_consent_chain(tmp_path)  # must not raise


def test_append_refuses_to_extend_broken_chain(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    path = tmp_path / "consent.jsonl"
    row = path.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(row.replace("subj-1", "subj-X") + "\n", encoding="utf-8")
    with pytest.raises(ChainTamperError):
        grant(tmp_path, "subj-2", "kb_promotion", OWNER)


# ── de-identify-or-refuse: the scrub is proven or it raises, value never echoed ─

def test_deidentify_removes_identifier(tmp_path):
    out = deidentify("Alex went to the park", ["Alex"])
    assert "Alex" not in out
    assert "park" in out


def test_deidentify_is_case_insensitive(tmp_path):
    out = deidentify("ALEX and alex and Alex", ["Alex"])
    assert "alex" not in out.lower()


def test_deidentify_ignores_empty_identifiers(tmp_path):
    out = deidentify("nothing to scrub", ["", None])  # type: ignore[list-item]
    assert out == "nothing to scrub"


def test_deidentify_error_never_carries_the_value():
    # if the scrub could somehow fail, the exception must not leak the secret.
    # force failure by monkeypatching is overkill; instead assert the contract on
    # the message of a deliberately-constructed failure.
    err = DeidentificationError("de-identification failed to clean the text")
    assert "failed to clean" in str(err)
    # the class contract: no value is ever formatted into the message by core.
    src = Path(core.__file__).read_text(encoding="utf-8")
    # the raise site must not interpolate `ident` or `out`/`text` into the message
    assert "raise DeidentificationError(" in src
    for bad in ("{ident", "{out", "{text", "{needle"):
        assert bad not in src, f"de-identification error must not echo {bad!r}"


# ── disclosure chain: the guardian's readable, tamper-evident record ──────────

def test_disclosure_roundtrips(tmp_path):
    record_disclosure(tmp_path, "subj-1", "lesson", "covered fractions")
    record_disclosure(tmp_path, "subj-1", "lesson", "covered decimals")
    rows = read_disclosures(tmp_path, "subj-1")
    assert [r["detail"] for r in rows] == ["covered fractions", "covered decimals"]


def test_disclosure_is_per_subject(tmp_path):
    record_disclosure(tmp_path, "subj-1", "lesson", "A")
    record_disclosure(tmp_path, "subj-2", "lesson", "B")
    assert [r["detail"] for r in read_disclosures(tmp_path, "subj-1")] == ["A"]
    assert [r["detail"] for r in read_disclosures(tmp_path, "subj-2")] == ["B"]


def test_disclosure_absent_is_empty(tmp_path):
    assert read_disclosures(tmp_path, "nobody") == []


def test_disclosure_tamper_raises(tmp_path):
    record_disclosure(tmp_path, "subj-1", "lesson", "A")
    # corrupt the CHAIN file (there is also a sibling .anchor.json now)
    ddir = tmp_path / "disclosures"
    f = next(p for p in ddir.iterdir() if p.suffix == ".jsonl")
    row = f.read_text(encoding="utf-8").splitlines()[0]
    f.write_text(row.replace("lesson", "surveillance") + "\n", encoding="utf-8")
    with pytest.raises(ChainTamperError):
        read_disclosures(tmp_path, "subj-1")


def test_disclosure_filename_does_not_leak_subject_id(tmp_path):
    record_disclosure(tmp_path, "very-identifying-name", "lesson", "A")
    names = [p.name for p in (tmp_path / "disclosures").iterdir()]
    assert all("very-identifying-name" not in n for n in names)


# ── boundary: core imports stdlib only (mirrors UTETY test_boundaries.py) ─────

_STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}


def test_core_imports_stdlib_only():
    """Static assertion: every top-level import in core.py resolves to the
    standard library. No willow_mcp runtime, no third-party, no network client
    may sneak into the child-device / stdlib-charter core."""
    src = Path(core.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                pytest.fail("core.py must have no relative (package-local) imports")
            if node.module:
                imported.add(node.module.split(".")[0])
    offenders = sorted(m for m in imported if m not in _STDLIB)
    assert not offenders, f"core.py imports non-stdlib modules: {offenders}"


def test_core_has_no_network_or_subprocess_imports():
    """Belt-and-suspenders over the allowlist: name the egress/exec modules
    explicitly so a future edit that adds one fails loudly, even if it is
    technically stdlib (socket, urllib, http, subprocess all are)."""
    src = Path(core.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib",
              "subprocess", "asyncio", "requests", "httpx", "aiohttp"}
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module.split(".")[0]]
        hit = sorted(set(mods) & banned)
        assert not hit, f"core.py must not import egress/exec modules: {hit}"


# ── truncation anchor (backported from UTETY audit B4) ────────────────────────

def test_disclosure_truncation_is_detected(tmp_path):
    """Deleting the newest rows leaves a chain that still LINKS cleanly — the
    anchor (head hash + count) is what catches it."""
    record_disclosure(tmp_path, "subj-1", "lesson", "A")
    record_disclosure(tmp_path, "subj-1", "lesson", "B")
    record_disclosure(tmp_path, "subj-1", "lesson", "C")
    f = next(p for p in (tmp_path / "disclosures").iterdir() if p.suffix == ".jsonl")
    lines = f.read_text(encoding="utf-8").splitlines()
    f.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # drop the tail
    with pytest.raises(ChainTamperError):
        read_disclosures(tmp_path, "subj-1")


def test_consent_truncation_denies_at_gate(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    grant(tmp_path, "subj-1", "person_inference", OWNER)
    path = tmp_path / "consent.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n", encoding="utf-8")  # drop the 2nd grant
    # links still clean, but count/head no longer match the anchor → deny
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)


def test_missing_anchor_on_nonempty_chain_is_tampered(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.anchor.json").unlink()  # anchor gone, rows remain
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False


def test_append_refuses_after_truncation(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    grant(tmp_path, "subj-1", "person_inference", OWNER)
    path = tmp_path / "consent.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n", encoding="utf-8")
    with pytest.raises(ChainTamperError):
        grant(tmp_path, "subj-2", "kb_promotion", OWNER)


# ── the COMPLETE truncation: emptied is not absent ────────────────────────────
#
# The count anchor catches "delete the newest rows". It cannot catch "delete ALL
# the rows" unless the reader can tell an emptied chain from one that never
# existed — `read_rows() -> None` means absent, and absent is legitimately not
# tampered. So a backend that returns None for both hands an attacker the
# strongest attack available *and* the simplest one: delete every row and the
# log reads as one that never existed. The revocation, the disclosure that names
# them — gone, silently.
#
# `FileBackend` writes `<root>/consent.jsonl` beside `<root>/consent.anchor.json`,
# so it has the same evidence marching-arts's SQLite backend has: an anchor with
# no rows beside it is positive evidence that rows WERE here. These tests pin
# that reading, and pin the one state that must still be absent — both gone.

def _consent_rows(tmp_path):
    """What the FileBackend itself reports for the consent chain."""
    return FileBackend(tmp_path).read_rows("consent")


def test_deleted_rows_file_beside_a_surviving_anchor_reads_as_emptied(tmp_path):
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.jsonl").unlink()          # every row deleted
    assert (tmp_path / "consent.anchor.json").is_file()  # the anchor survives

    assert _consent_rows(tmp_path) == []           # emptied, NOT None/absent
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)             # and it says so out loud


def test_deleted_disclosure_rows_file_raises_rather_than_reading_empty(tmp_path):
    """A guardian's record that was emptied must announce it, not return []."""
    record_disclosure(tmp_path, "subj-1", "lesson", "A")
    record_disclosure(tmp_path, "subj-1", "lesson", "B")
    f = next(p for p in (tmp_path / "disclosures").iterdir() if p.suffix == ".jsonl")
    f.unlink()
    with pytest.raises(ChainTamperError):
        read_disclosures(tmp_path, "subj-1")


def test_emptied_rows_file_with_a_surviving_anchor_is_tampered(tmp_path):
    """The file left in place but truncated to nothing — same attack, one syscall
    different. Already caught; pinned so it stays caught."""
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.jsonl").write_text("", encoding="utf-8")
    assert _consent_rows(tmp_path) == []
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)


def test_unreadable_rows_file_beside_an_anchor_is_tampered_not_absent(tmp_path):
    """Unparseable is not absent either: an anchor beside a garbage rows file is
    the same evidence. Fail closed — ambiguous reads as tampered."""
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.jsonl").write_text("{not json at all\n", encoding="utf-8")
    assert _consent_rows(tmp_path) == []
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)


def test_deleted_anchor_with_rows_present_is_still_tampered(tmp_path):
    """The mirror image: rows are evidence of an anchor just as an anchor is
    evidence of rows. `read_rows` must keep reporting the rows it has."""
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.anchor.json").unlink()
    assert len(_consent_rows(tmp_path)) == 1       # not None, not []
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)


def test_both_files_gone_is_genuinely_absent(tmp_path):
    """The one state that must NOT read as tampered: nothing is left to say a
    chain was ever here, and a store that was never written is clean."""
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.jsonl").unlink()
    (tmp_path / "consent.anchor.json").unlink()
    assert _consent_rows(tmp_path) is None
    assert permitted(tmp_path, "subj-1", "kb_promotion") is False
    verify_consent_chain(tmp_path)                 # must not raise


def test_never_written_chain_is_absent(tmp_path):
    assert _consent_rows(tmp_path) is None
    assert FileBackend(tmp_path).read_rows("disclosure/deadbeef") is None


def test_append_refuses_to_rebuild_a_chain_whose_rows_were_deleted(tmp_path):
    """Otherwise the next honest grant launders the attack: it would start a new
    chain at genesis and overwrite the orphaned anchor with count=1, and the
    store would verify clean afterwards with the deleted history gone."""
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    (tmp_path / "consent.jsonl").unlink()
    with pytest.raises(ChainTamperError):
        grant(tmp_path, "subj-2", "kb_promotion", OWNER)
    # the anchor was not advanced, so the evidence is still there afterwards
    assert json.loads((tmp_path / "consent.anchor.json").read_text())["count"] == 1
    with pytest.raises(ChainTamperError):
        verify_consent_chain(tmp_path)


def test_append_still_starts_a_genuinely_absent_chain(tmp_path):
    """The refusal above must not make a fresh store unwritable."""
    grant(tmp_path, "subj-1", "kb_promotion", OWNER)
    assert permitted(tmp_path, "subj-1", "kb_promotion") is True


# ── pluggable backend: the same logic over a non-file store ───────────────────

class DictBackend:
    """An in-memory Backend — proves the chain logic is storage-free (the shape
    UTETY's SQLite backend fills). Satisfies the Backend protocol structurally."""
    def __init__(self):
        self.rows: dict[str, list[dict]] = {}
        self.anchors: dict[str, dict] = {}

    def read_rows(self, chain):
        return list(self.rows[chain]) if chain in self.rows else None

    def append_row(self, chain, row):
        self.rows.setdefault(chain, []).append(row)

    def read_anchor(self, chain):
        return dict(self.anchors[chain]) if chain in self.anchors else None

    def write_anchor(self, chain, anchor):
        self.anchors[chain] = dict(anchor)


def test_backend_protocol_accepts_a_custom_backend():
    from subject_consent.core import Backend
    assert isinstance(DictBackend(), Backend)


def test_full_lifecycle_over_dict_backend():
    b = DictBackend()
    assert permitted(b, "s1", "kb_promotion") is False
    grant(b, "s1", "kb_promotion", "guardian")
    assert permitted(b, "s1", "kb_promotion") is True
    revoke(b, "s1", "kb_promotion", "guardian")
    assert permitted(b, "s1", "kb_promotion") is False
    record_disclosure(b, "s1", "lesson", "fractions")
    assert [r["detail"] for r in read_disclosures(b, "s1")] == ["fractions"]
    verify_consent_chain(b)  # intact → no raise


def test_dict_backend_truncation_detected():
    b = DictBackend()
    grant(b, "s1", "kb_promotion", "guardian")
    grant(b, "s1", "person_inference", "guardian")
    b.rows["consent"] = b.rows["consent"][:1]  # truncate, leave stale anchor
    assert permitted(b, "s1", "kb_promotion") is False


# ── the emptied chain is refused on WRITE, for every backend ──────────────────
#
# `read_rows` distinguishes None ("absent") from [] ("present but empty"), and
# that distinction is the whole defence against the complete truncation. But
# `_append` used to read `read_rows(chain) or []`, collapsing the two — and
# since [] is falsy the guard was skipped, so no backend could make the write
# path refuse an emptied chain however carefully it reported one.
#
# The failure was worse than a missed detection. `verify` caught the wipe, and
# then the next honest append restarted at genesis, overwrote the orphaned
# anchor with count=1, and the store verified clean with the deleted history
# gone. The detection window was real and SELF-CLOSING: any legitimate write
# laundered it. These tests are the closing of that window.

def _wiped():
    """Two granted transitions, then every row deleted and the anchor left."""
    b = DictBackend()
    grant(b, "s1", "local_only", "guardian")
    grant(b, "s1", "kb_promotion", "guardian")
    b.rows[core._CONSENT_CHAIN] = []          # emptied, anchor survives
    return b


def test_an_emptied_chain_refuses_the_next_append():
    b = _wiped()
    with pytest.raises(core.ChainTamperError):
        grant(b, "s1", "person_inference", "guardian")


def test_the_orphaned_anchor_survives_the_refused_append():
    """The point of refusing: the evidence must still be there afterwards. If the
    append had gone through it would have overwritten count=2 with count=1."""
    b = _wiped()
    with pytest.raises(core.ChainTamperError):
        grant(b, "s1", "local_only", "guardian")
    assert b.anchors[core._CONSENT_CHAIN]["count"] == 2
    with pytest.raises(core.ChainTamperError):
        core.verify_consent_chain(b)


def test_a_wiped_chain_cannot_be_laundered_by_an_honest_write():
    """End to end, the attack as it would actually be run: delete the rows, then
    wait for anybody to do something ordinary."""
    b = _wiped()
    with pytest.raises(core.ChainTamperError):
        grant(b, "s1", "local_only", "guardian")
    assert permitted(b, "s1", "kb_promotion") is False
    with pytest.raises(core.ChainTamperError):
        core.verify_consent_chain(b)


def test_an_emptied_disclosure_chain_is_refused_too():
    b = DictBackend()
    core.record_disclosure(b, "s1", "read", "leader")
    chain = core._disclosure_chain("s1")
    b.rows[chain] = []
    with pytest.raises(core.ChainTamperError):
        core.record_disclosure(b, "s1", "read", "leader")


def test_a_genuinely_absent_chain_still_starts_at_genesis():
    """The control. Without it, 'refuse everything' passes every test above and
    a first grant would be impossible."""
    b = DictBackend()
    c = grant(b, "fresh", "local_only", "guardian")
    assert c.status == core.GRANTED
    assert permitted(b, "fresh", "local_only") is True
    assert b.anchors[core._CONSENT_CHAIN]["count"] == 1
