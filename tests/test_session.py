"""Tests for stores/session.py — store-native session tokens (D11).

Same loading pattern as tests/test_principal.py: load the module directly
from stores/, no package install. Every test builds its own store root under
tmp_path — nothing here ever touches the real stores/.sessions.

The adversarial bar these are written to, mirroring test_principal.py's own
framing: it is not enough that the happy path works. A session layer that
stores raw tokens on disk, that leaks (via timing or exception type) which
of "unknown" / "expired" / "revoked" a bad token was, or that corrupts under
concurrent minting, has failed at the one job this module has — so each of
those gets its own section below, not just a mint/verify smoke test.
"""
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("session", _REPO / "stores" / "session.py")
session = importlib.util.module_from_spec(_spec)
sys.modules["session"] = session
_spec.loader.exec_module(session)

principal = session.principal  # the same principal.py session.py itself loaded

GOOD_BUILDER_ID = "a" * 32  # path-safe under principal.py's _check_builder_id


def _store(tmp_path):
    return session.FilesystemSessionStore(tmp_path / "sessions")


# ── mint / verify round trip ─────────────────────────────────────────────────

def test_mint_then_verify_returns_the_correct_builder_id(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    assert minted.token
    assert minted.builder_id == GOOD_BUILDER_ID
    assert session.verify_session(store, minted.token) == GOOD_BUILDER_ID


def test_two_mints_for_the_same_builder_id_produce_different_tokens(tmp_path):
    store = _store(tmp_path)
    first = session.mint_session(store, GOOD_BUILDER_ID)
    second = session.mint_session(store, GOOD_BUILDER_ID)
    assert first.token != second.token
    assert session.verify_session(store, first.token) == GOOD_BUILDER_ID
    assert session.verify_session(store, second.token) == GOOD_BUILDER_ID


def test_mint_rejects_a_non_positive_ttl(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(session.SessionError, match="ttl_seconds"):
        session.mint_session(store, GOOD_BUILDER_ID, ttl_seconds=0)
    with pytest.raises(session.SessionError, match="ttl_seconds"):
        session.mint_session(store, GOOD_BUILDER_ID, ttl_seconds=-5)
    assert store.all_token_hashes() == []


# ── unknown / garbage tokens ─────────────────────────────────────────────────

def test_an_unknown_token_verifies_to_none(tmp_path):
    store = _store(tmp_path)
    assert session.verify_session(store, "totally-made-up-token") is None


def test_a_garbage_token_verifies_to_none_not_an_exception(tmp_path):
    store = _store(tmp_path)
    for garbage in ["", "../../etc/passwd", "a" * 5000, "\x00\x00", "🎉🎉🎉"]:
        if garbage == "":
            # empty string is refused outright (not a well-formed token at
            # all) — everything else is a well-formed-but-unknown token and
            # must resolve to None, not raise.
            with pytest.raises(session.SessionError):
                session.verify_session(store, garbage)
            continue
        assert session.verify_session(store, garbage) is None


def test_verify_does_not_create_anything_on_disk(tmp_path):
    store = _store(tmp_path)
    session.verify_session(store, "some-token-nobody-ever-minted")
    assert store.all_token_hashes() == []


# ── expiry, checked against a real clock at verify time ──────────────────────

def test_an_expired_session_verifies_to_none_even_though_its_row_still_exists(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID, ttl_seconds=1, now=1_000_000.0)

    # the row is genuinely still on disk — this is expiry, not deletion
    record = store.get_session(session._token_hash(minted.token))
    assert record is not None
    assert record.revoked_at is None

    # but a verify call whose clock has moved past expires_at refuses it
    assert session.verify_session(store, minted.token, now=1_000_002.0) is None


def test_a_session_minted_with_a_negative_ttl_would_be_refused_at_mint_not_verify(tmp_path):
    """ttl_seconds <= 0 is refused by mint_session itself (see the ttl test
    above) — expiry is enforced at verify time for a session that WAS
    validly minted and later aged out, not used as a backdoor way to mint
    an already-dead one."""
    store = _store(tmp_path)
    with pytest.raises(session.SessionError):
        session.mint_session(store, GOOD_BUILDER_ID, ttl_seconds=-1, now=1_000_000.0)


def test_expiry_is_checked_against_the_real_clock_by_default(tmp_path, monkeypatch):
    """Not just the injectable `now=` path — the production path (no `now`
    passed at all) must also enforce expiry against `time.time()`."""
    store = _store(tmp_path)
    fake_now = [1_000_000.0]
    monkeypatch.setattr(session.time, "time", lambda: fake_now[0])

    minted = session.mint_session(store, GOOD_BUILDER_ID, ttl_seconds=10)
    assert session.verify_session(store, minted.token) == GOOD_BUILDER_ID

    fake_now[0] += 20  # advance past expiry with no `now=` override anywhere
    assert session.verify_session(store, minted.token) is None


def test_a_session_still_within_its_ttl_verifies_successfully(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID, ttl_seconds=100, now=1_000_000.0)
    assert session.verify_session(store, minted.token, now=1_000_050.0) == GOOD_BUILDER_ID
    # exactly-at-expiry is expired, not valid — a half-open window
    assert session.verify_session(store, minted.token, now=1_000_100.0) is None


# ── revocation ───────────────────────────────────────────────────────────────

def test_revoke_makes_a_previously_valid_token_verify_to_none_immediately(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    assert session.verify_session(store, minted.token) == GOOD_BUILDER_ID

    session.revoke_session(store, minted.token)
    assert session.verify_session(store, minted.token) is None


def test_revoking_twice_is_not_an_error(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    session.revoke_session(store, minted.token)
    session.revoke_session(store, minted.token)  # must not raise
    assert session.verify_session(store, minted.token) is None


def test_revoking_an_unknown_token_is_a_silent_no_op(tmp_path):
    """No leak: revoking something that was never minted must not raise or
    otherwise announce that the token doesn't exist — see module docstring,
    "don't leak which case it was," applied to the write side."""
    store = _store(tmp_path)
    session.revoke_session(store, "never-minted-token")  # must not raise
    assert store.all_token_hashes() == []


def test_revoking_one_session_does_not_affect_a_sibling_session(tmp_path):
    store = _store(tmp_path)
    first = session.mint_session(store, GOOD_BUILDER_ID)
    second = session.mint_session(store, GOOD_BUILDER_ID)
    session.revoke_session(store, first.token)
    assert session.verify_session(store, first.token) is None
    assert session.verify_session(store, second.token) == GOOD_BUILDER_ID


def test_revocation_records_a_timestamp_and_keeps_the_first_one(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    session.revoke_session(store, minted.token, now=500.0)
    session.revoke_session(store, minted.token, now=999.0)  # idempotent, first stands
    record = store.get_session(session._token_hash(minted.token))
    assert record.revoked_at == 500.0


# ── the raw token must never land on disk ────────────────────────────────────

def test_the_raw_token_never_appears_anywhere_under_the_store_root(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    session.revoke_session(store, minted.token)  # exercise the write path twice

    for path in tmp_path.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        assert minted.token.encode("utf-8") not in raw, f"raw token leaked into {path}"
        # and not url-safe-b64-partial or otherwise substring-detectable
        assert minted.token not in raw.decode("utf-8", errors="ignore")


def test_the_stored_row_holds_a_hash_not_the_raw_token(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    record = store.get_session(session._token_hash(minted.token))
    assert record.token_hash == session._token_hash(minted.token)
    assert record.token_hash != minted.token
    assert len(record.token_hash) == 64  # sha256 hex digest


# ── builder_id validation reuses principal.py, doesn't reimplement it ────────

@pytest.mark.parametrize("bad", ["../../etc/passwd", "", "a b", "a/b", ".hidden", "-lead"])
def test_mint_refuses_a_builder_id_that_fails_principals_own_charset_check(tmp_path, bad):
    store = _store(tmp_path)
    with pytest.raises(session.SessionError):
        session.mint_session(store, bad)
    # nothing was minted for the malformed identity
    assert store.all_token_hashes() == []
    # and the same input is refused by principal.py's own check directly,
    # confirming session.py is reusing that rule rather than a looser copy
    with pytest.raises(principal.PrincipalError):
        principal._check_builder_id(bad)


def test_mint_refuses_a_non_string_builder_id(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(session.SessionError):
        session.mint_session(store, None)
    with pytest.raises(session.SessionError):
        session.mint_session(store, 4242)
    assert store.all_token_hashes() == []


def test_verify_session_never_silently_succeeds_for_a_store_holding_a_malformed_builder_id(tmp_path):
    """A row that somehow got a bad builder_id written into it (corruption,
    a store implementation that skipped validation) must fail closed when
    read back, not hand out a malformed identity as if it were legitimate."""
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    path = store._session_path(session._token_hash(minted.token))
    row = __import__("json").loads(path.read_text())
    row["builder_id"] = "../../etc/passwd"
    path.write_text(__import__("json").dumps(row))
    with pytest.raises(session.SessionError):
        session.verify_session(store, minted.token)


# ── store integrity ──────────────────────────────────────────────────────────

def test_store_refuses_a_symlinked_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(session.SessionError, match="symlink"):
        session.FilesystemSessionStore(link)


def test_corrupt_row_fails_closed_not_with_a_traceback(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    path = store._session_path(session._token_hash(minted.token))
    path.write_text("{not valid json")
    with pytest.raises(session.SessionError, match="corrupt"):
        store.get_session(session._token_hash(minted.token))


def test_insert_session_refuses_to_overwrite_an_existing_row(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    record = store.get_session(session._token_hash(minted.token))
    with pytest.raises(session.SessionError, match="overwrite"):
        store.insert_session(record)


def test_a_tampered_row_that_claims_a_different_token_hash_is_refused(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    path = store._session_path(session._token_hash(minted.token))
    row = __import__("json").loads(path.read_text())
    row["token_hash"] = "0" * 64
    path.write_text(__import__("json").dumps(row))
    with pytest.raises(session.SessionError, match="inconsistent"):
        store.get_session(session._token_hash(minted.token))


# ── concurrency ──────────────────────────────────────────────────────────────

def test_concurrent_mints_do_not_corrupt_the_store_or_drop_a_session(tmp_path):
    """Mirrors test_principal.py's concurrent-first-login test in spirit:
    many callers hitting the same store at once must not corrupt it, and
    every session that was reported as minted must actually be verifiable
    afterward — none silently dropped."""
    store = _store(tmp_path)
    parties = 32
    results = [None] * parties
    errors = [None] * parties

    def worker(i):
        try:
            results[i] = session.mint_session(store, GOOD_BUILDER_ID)
        except BaseException as e:  # noqa: BLE001 - recorded and re-raised below
            errors[i] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(parties)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert [e for e in errors if e is not None] == []
    tokens = {r.token for r in results}
    assert len(tokens) == parties  # no two callers minted the same token

    assert len(store.all_token_hashes()) == parties
    for r in results:
        assert session.verify_session(store, r.token) == GOOD_BUILDER_ID


def test_concurrent_revokes_of_the_same_token_do_not_corrupt_the_store(tmp_path):
    store = _store(tmp_path)
    minted = session.mint_session(store, GOOD_BUILDER_ID)
    errors = []

    def worker():
        try:
            session.revoke_session(store, minted.token)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert session.verify_session(store, minted.token) is None
    record = store.get_session(session._token_hash(minted.token))
    assert record.revoked_at is not None


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_mint_verify_revoke(tmp_path, capsys):
    root = str(tmp_path / "sessions")
    assert session.main(["--root", root, "mint", GOOD_BUILDER_ID]) == 0
    token = __import__("json").loads(capsys.readouterr().out)["token"]

    assert session.main(["--root", root, "verify", token]) == 0
    assert capsys.readouterr().out.strip() == GOOD_BUILDER_ID

    assert session.main(["--root", root, "revoke", token]) == 0
    capsys.readouterr()

    assert session.main(["--root", root, "verify", token]) == 1
    assert "invalid" in capsys.readouterr().out

    assert session.main(["--root", root, "mint", "../bad"]) == 1


# ---------------------------------------------------------------------------
# A token that begins with "-" (base64url allows it, ~1 in 64)
#
# Found as a 1.6%-per-run CI flake: `session.py verify <token>` died with "the
# following arguments are required: token" — naming the argument the user had
# just supplied. Two halves, because either alone leaves a hole: new tokens
# stop starting with "-", and the CLI handles one anyway, since tokens minted
# before the change are still valid and have to stay usable.
# ---------------------------------------------------------------------------

def test_mint_rejects_a_token_that_begins_with_a_hyphen(monkeypatch):
    # Deterministic, not statistical: hand the generator's first draw back as a
    # hyphen token and require _mint_token to draw again.
    draws = iter(["-leading-hyphen-token", "safe-token-value"])
    monkeypatch.setattr(session.secrets, "token_urlsafe", lambda _n: next(draws))
    assert session._mint_token() == "safe-token-value"


def test_mint_gives_up_loudly_rather_than_looping_forever(monkeypatch):
    # A wedged mint is worse than a failed one: bound the rejection sampling.
    monkeypatch.setattr(session.secrets, "token_urlsafe", lambda _n: "-always")
    with pytest.raises(session.SessionError, match="not behaving randomly"):
        session._mint_token()


def test_minting_is_still_random_and_still_hyphen_free(tmp_path):
    # The guard must not have quietly replaced randomness with a fixed value.
    store = _store(tmp_path)
    tokens = {session.mint_session(store, GOOD_BUILDER_ID).token for _ in range(50)}
    assert len(tokens) == 50
    assert not any(t.startswith("-") for t in tokens)


@pytest.mark.parametrize("command", ["verify", "revoke"])
def test_cli_accepts_a_legacy_token_that_begins_with_a_hyphen(tmp_path, capsys,
                                                              monkeypatch, command):
    root = str(tmp_path / "sessions")
    legacy = "-Ab1_cD2efGh3IjKlMn4opQrS5tUvWxYz6"
    # Patch the minter itself, not the generator: patching the generator would
    # make _mint_token reject forever, which is the behaviour tested above.
    monkeypatch.setattr(session, "_mint_token", lambda: legacy)
    assert session.main(["--root", root, "mint", GOOD_BUILDER_ID]) == 0
    token = __import__("json").loads(capsys.readouterr().out)["token"]
    assert token == legacy
    monkeypatch.undo()

    # The exact call that was failing 1.6% of the time in CI.
    assert session.main(["--root", root, command, token]) == 0


def test_the_token_guard_leaves_ordinary_argv_alone():
    guard = session._argv_with_token_guard
    assert guard(["--root", "r", "verify", "t"]) == ["--root", "r", "verify", "--", "t"]
    assert guard(["--root", "r", "mint", "b"]) == ["--root", "r", "mint", "b"]
    already = ["verify", "--", "-tok"]                  # no second separator
    assert guard(already) == already
    # A session root literally named "verify" is a path, not the subcommand.
    assert guard(["--root", "verify", "mint", "b"]) == ["--root", "verify", "mint", "b"]
