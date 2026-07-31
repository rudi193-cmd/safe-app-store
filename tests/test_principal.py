"""Tests for stores/principal.py — store-minted identity (D11).

Same loading pattern as tests/test_sap_gate.py: load the module directly
from stores/, no package install. Every test builds its own store root under
tmp_path — nothing here ever touches the real stores/.principals.

The adversarial bar these are written to: it is not enough that the happy
path works. D11 exists because an earlier design let GitHub own the store's
identity namespace, and the fix is only real if (a) the uniqueness
constraints survive being attacked rather than merely exercised, (b) a lost
first-login race cannot leave an orphaned identity behind, and (c) nothing
anywhere lets an `external_id` do the job of a `builder_id`. Each of those
has its own section below.
"""
import importlib.util
import json
import multiprocessing
import re
import sys
import threading
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("principal", _REPO / "stores" / "principal.py")
principal = importlib.util.module_from_spec(_spec)
# dataclasses' own typing introspection looks the module up in sys.modules
# while exec_module is still running - it has to be registered first.
sys.modules["principal"] = principal
_spec.loader.exec_module(principal)

GH = "github"


def _store(tmp_path):
    return principal.FilesystemPrincipalStore(tmp_path / "principals")


# ── minting ──────────────────────────────────────────────────────────────────

def test_minted_builder_id_is_path_safe_and_unique():
    seen = {principal.mint_builder_id() for _ in range(500)}
    assert len(seen) == 500  # 128 bits; a collision here means the generator changed
    pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    for builder_id in seen:
        assert pattern.match(builder_id), builder_id
        assert len(builder_id) >= 32  # 16 bytes, hex
        assert "/" not in builder_id and ".." not in builder_id


def test_mint_rejects_its_own_generator_if_it_ever_produces_an_unsafe_id(monkeypatch):
    """The belt-and-suspenders check the module documents: `mint_builder_id`
    validates the id it generated itself, so a future edit to the generator
    (a uuid with dashes is fine, base64 with a '/' is not, a prefix that
    starts with '.' is not) is caught here rather than in D6's
    apps/<builder_id>/ path."""
    monkeypatch.setattr(principal.secrets, "token_hex", lambda n: "../../etc/passwd")
    with pytest.raises(principal.PrincipalError, match="path-safety charset"):
        principal.mint_builder_id()

    monkeypatch.setattr(principal.secrets, "token_hex", lambda n: "")
    with pytest.raises(principal.PrincipalError, match="path-safety charset"):
        principal.mint_builder_id()

    monkeypatch.setattr(principal.secrets, "token_hex", lambda n: ".hidden")
    with pytest.raises(principal.PrincipalError, match="path-safety charset"):
        principal.mint_builder_id()


# ── first login / returning login ────────────────────────────────────────────

def test_first_login_mints_and_binds(tmp_path):
    store = _store(tmp_path)
    result = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    assert result.created is True
    assert result.authenticator.provider == GH
    assert result.authenticator.external_id == "4242"
    assert result.authenticator.builder_id == result.builder_id
    assert store.get_principal(result.builder_id) is not None


def test_returning_login_resolves_to_the_same_builder_id(tmp_path):
    store = _store(tmp_path)
    first = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    for _ in range(5):
        again = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
        assert again.builder_id == first.builder_id
        assert again.created is False
    assert store.all_builder_ids() == [first.builder_id]  # exactly one identity, ever


def test_two_different_accounts_get_two_different_builder_ids(tmp_path):
    store = _store(tmp_path)
    a = principal.resolve_verified_identity(store, provider=GH, external_id="1")
    b = principal.resolve_verified_identity(store, provider=GH, external_id="2")
    assert a.builder_id != b.builder_id
    assert sorted(store.all_builder_ids()) == sorted([a.builder_id, b.builder_id])


def test_lookup_of_an_unknown_authenticator_returns_none_not_an_exception(tmp_path):
    store = _store(tmp_path)
    assert principal.lookup_builder_id(store, provider=GH, external_id="99999") is None
    principal.resolve_verified_identity(store, provider=GH, external_id="1")
    assert principal.lookup_builder_id(store, provider=GH, external_id="99999") is None


def test_lookup_finds_a_registered_account(tmp_path):
    store = _store(tmp_path)
    result = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    assert principal.lookup_builder_id(store, provider=GH, external_id="4242") == result.builder_id


def test_provider_case_does_not_split_one_account_into_two_identities(tmp_path):
    """Normalization is load-bearing, not cosmetic: if "GitHub" and "github"
    were distinct keys, the same human would get a second builder_id — and a
    second apps/<builder_id>/, a second keyring, a second Nestor db —
    depending on how the callback happened to spell the provider."""
    store = _store(tmp_path)
    first = principal.resolve_verified_identity(store, provider="GitHub", external_id="4242")
    again = principal.resolve_verified_identity(store, provider="github", external_id="4242")
    assert again.builder_id == first.builder_id
    assert again.created is False
    assert store.all_builder_ids() == [first.builder_id]


# ── uniqueness, attacked rather than exercised ───────────────────────────────

def test_rebinding_an_external_identity_to_a_second_builder_is_refused(tmp_path):
    """The exact mechanism D11 names as the fix. Not "seems to work": the
    victim's binding must be *unchanged* afterwards, and the attacker's
    builder_id must not appear anywhere."""
    store = _store(tmp_path)
    victim = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    attacker = principal.resolve_verified_identity(store, provider=GH, external_id="6666")

    with pytest.raises(principal.AuthenticatorConflict, match="already bound"):
        principal.bind_authenticator(
            store, provider=GH, external_id="4242", builder_id=attacker.builder_id
        )

    assert principal.lookup_builder_id(store, provider=GH, external_id="4242") == victim.builder_id
    auth = store.get_authenticator(GH, "4242")
    assert auth.builder_id == victim.builder_id
    assert auth.linked_at == victim.authenticator.linked_at  # not even touched


def test_conflict_carries_the_row_that_holds_the_ground(tmp_path):
    store = _store(tmp_path)
    victim = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    other = principal.resolve_verified_identity(store, provider=GH, external_id="6666")
    with pytest.raises(principal.AuthenticatorConflict) as excinfo:
        principal.bind_authenticator(
            store, provider=GH, external_id="4242", builder_id=other.builder_id
        )
    assert excinfo.value.existing.builder_id == victim.builder_id


def test_binding_a_second_authenticator_to_an_existing_builder_is_refused(tmp_path):
    """Constraint 2, and the "attach my account to your builder" takeover.
    D11 v1 is one authenticator per builder_id, permanently."""
    store = _store(tmp_path)
    victim = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    with pytest.raises(principal.AuthenticatorConflict, match="already has an authenticator"):
        principal.bind_authenticator(
            store, provider=GH, external_id="9999", builder_id=victim.builder_id
        )
    # and the attacker's account is still unregistered — no partial write
    assert principal.lookup_builder_id(store, provider=GH, external_id="9999") is None
    assert store.get_authenticator_for_builder(victim.builder_id).external_id == "4242"


def test_rebinding_the_same_pair_to_the_same_builder_is_idempotent(tmp_path):
    """Re-login must not be an error. It must also not mint a second
    identity or rewrite linked_at."""
    store = _store(tmp_path)
    first = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    for _ in range(3):
        again = principal.bind_authenticator(
            store, provider=GH, external_id="4242", builder_id=first.builder_id
        )
        assert again.builder_id == first.builder_id
        assert again.linked_at == first.authenticator.linked_at
    assert store.all_builder_ids() == [first.builder_id]


def test_binding_to_a_builder_the_store_never_minted_is_refused(tmp_path):
    """A binding must point at an identity that actually exists — otherwise
    a caller could invent a builder_id (say, one it read off a directory
    listing of apps/) and bind itself to it."""
    store = _store(tmp_path)
    with pytest.raises(principal.PrincipalError, match="never minted"):
        principal.bind_authenticator(
            store, provider=GH, external_id="4242", builder_id=principal.mint_builder_id()
        )
    assert principal.lookup_builder_id(store, provider=GH, external_id="4242") is None


def test_uniqueness_survives_a_reopened_store(tmp_path):
    """The constraint is durable state, not an in-memory set that a process
    restart forgets."""
    store = _store(tmp_path)
    first = principal.resolve_verified_identity(store, provider=GH, external_id="4242")

    reopened = _store(tmp_path)
    again = principal.resolve_verified_identity(reopened, provider=GH, external_id="4242")
    assert again.builder_id == first.builder_id
    assert again.created is False

    third = _store(tmp_path)
    other = principal.resolve_verified_identity(third, provider=GH, external_id="7")
    with pytest.raises(principal.AuthenticatorConflict):
        principal.bind_authenticator(
            third, provider=GH, external_id="4242", builder_id=other.builder_id
        )


# ── the concurrent-first-login race ──────────────────────────────────────────

class _BarrierStore:
    """Wraps the real store and holds every caller at a barrier *between*
    minting and inserting, so all N callers reach `insert_authenticator`
    holding different freshly-minted builder_ids for the same brand-new
    account. Without this the race is real but rare; with it, it happens on
    every run. Works for threads or processes depending on which flavour of
    barrier is handed in."""

    def __init__(self, inner, barrier):
        self._inner = inner
        self._barrier = barrier

    def get_principal(self, builder_id):
        return self._inner.get_principal(builder_id)

    def get_authenticator(self, provider, external_id):
        return self._inner.get_authenticator(provider, external_id)

    def get_authenticator_for_builder(self, builder_id):
        return self._inner.get_authenticator_for_builder(builder_id)

    def insert_authenticator(self, auth, *, new_principal=None):
        if new_principal is not None:
            self._barrier.wait(timeout=30)
        return self._inner.insert_authenticator(auth, new_principal=new_principal)


def test_concurrent_first_login_yields_one_builder_id_and_no_orphans(tmp_path):
    """The bug class this design exists to make unrepresentable: two
    requests for the same brand-new GitHub account arriving at once, each
    minting its own builder_id, one of which becomes an identity nobody can
    ever log into — possibly after apps/<builder_id>/ and a signing key were
    already provisioned behind it.

    All 16 callers must agree on one builder_id, exactly one may report
    created=True, and the store must contain exactly one principal — not
    sixteen, not two."""
    parties = 16
    inner = _store(tmp_path)
    store = _BarrierStore(inner, threading.Barrier(parties, timeout=30))
    results = [None] * parties
    errors = [None] * parties

    def worker(i):
        try:
            results[i] = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
        except BaseException as e:  # noqa: BLE001 - recorded and re-raised below
            errors[i] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(parties)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert [e for e in errors if e is not None] == []
    builder_ids = {r.builder_id for r in results}
    assert len(builder_ids) == 1, f"the race produced {len(builder_ids)} identities"
    assert sum(1 for r in results if r.created) == 1
    assert inner.all_builder_ids() == list(builder_ids)  # no orphaned principal rows


def _child_login(root, external_id, barrier, out):
    spec = importlib.util.spec_from_file_location("principal", _REPO / "stores" / "principal.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["principal"] = mod
    spec.loader.exec_module(mod)
    store = _BarrierStore(mod.FilesystemPrincipalStore(Path(root)), barrier)
    result = mod.resolve_verified_identity(store, provider="github", external_id=external_id)
    out.put((result.builder_id, result.created))


def test_concurrent_first_login_across_processes(tmp_path):
    """Threads within one interpreter are the easy case. Separate processes
    are what actually exercises `flock` — a store whose uniqueness lived in
    a per-process set, or in a lock that only serializes threads, passes the
    test above and fails this one. Same barrier, so the collision is
    deterministic here too; same invariant: one identity, one creator, no
    orphans."""
    parties = 8
    ctx = multiprocessing.get_context("spawn")
    out = ctx.Queue()
    barrier = ctx.Barrier(parties, timeout=60)
    root = str(tmp_path / "principals")
    procs = [
        ctx.Process(target=_child_login, args=(root, "4242", barrier, out))
        for _ in range(parties)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=120)
    assert all(p.exitcode == 0 for p in procs), [p.exitcode for p in procs]

    seen = [out.get(timeout=30) for _ in procs]
    builder_ids = {b for b, _ in seen}
    assert len(builder_ids) == 1, f"the race produced {len(builder_ids)} identities"
    assert sum(1 for _, created in seen if created) == 1
    assert _store(tmp_path).all_builder_ids() == list(builder_ids)


# ── a store that lies about what it did ──────────────────────────────────────

class _OverwritingStore:
    """A store that silently overwrites an existing binding instead of
    refusing — i.e. one that implements the *shape* of the Protocol without
    the constraint. The identity core must not take its word for it."""

    def __init__(self, inner):
        self._inner = inner
        self.rows = {}
        self.principals = {}

    def get_principal(self, builder_id):
        return self.principals.get(builder_id)

    def get_authenticator(self, provider, external_id):
        return self.rows.get((provider, external_id))

    def get_authenticator_for_builder(self, builder_id):
        for row in self.rows.values():
            if row.builder_id == builder_id:
                return row
        return None

    def insert_authenticator(self, auth, *, new_principal=None):
        self.rows[auth.key()] = auth  # the bug: no constraint at all
        if new_principal is not None:
            self.principals[new_principal.builder_id] = new_principal
        return auth


def test_a_store_that_overwrites_bindings_is_caught_not_trusted(tmp_path):
    """An overwriting store hands back a perfectly plausible row. The
    read-back in the core is what turns "the call returned" into "the
    binding is actually what I asked for" — here it cannot save the victim
    (the store already clobbered the row), so what is asserted is that the
    module does not silently report success on a store whose reverse index
    disagrees, and, more importantly, that the real store does not behave
    this way (see the test above it)."""
    store = _OverwritingStore(_store(tmp_path))
    victim = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    attacker_id = principal.mint_builder_id()
    store.principals[attacker_id] = principal.Principal(builder_id=attacker_id, minted_at=0.0)

    # the broken store lets the takeover through; the real one refuses it
    principal.bind_authenticator(store, provider=GH, external_id="4242", builder_id=attacker_id)
    assert store.get_authenticator(GH, "4242").builder_id == attacker_id

    real = _store(tmp_path / "real")
    real_victim = principal.resolve_verified_identity(real, provider=GH, external_id="4242")
    real_attacker = principal.resolve_verified_identity(real, provider=GH, external_id="6666")
    with pytest.raises(principal.AuthenticatorConflict):
        principal.bind_authenticator(
            real, provider=GH, external_id="4242", builder_id=real_attacker.builder_id
        )
    assert principal.lookup_builder_id(real, provider=GH, external_id="4242") == real_victim.builder_id
    assert victim.builder_id != attacker_id


class _NonAtomicStore:
    """The naive two-step implementation the Protocol forbids: write the
    principal row, *then* discover the authenticator conflict. Reproduces
    the race precisely — the initial read misses (as it would when the
    winner has not committed yet), so the core mints and inserts, and only
    the insert learns it lost. A store built this way leaves exactly the
    orphan the design reasons about: a real identity with nothing that can
    ever authenticate into it."""

    def __init__(self, inner, squatter):
        self._inner = inner
        self._squatter = squatter
        self._raced = False

    def get_principal(self, builder_id):
        return self._inner.get_principal(builder_id)

    def get_authenticator(self, provider, external_id):
        if not self._raced:
            return None  # the stale read that opens the race window
        return self._inner.get_authenticator(provider, external_id)

    def get_authenticator_for_builder(self, builder_id):
        return self._inner.get_authenticator_for_builder(builder_id)

    def insert_authenticator(self, auth, *, new_principal=None):
        self._raced = True
        if new_principal is not None:
            # persist the principal first, as a naive implementation would
            self._inner._write_json(  # noqa: SLF001 - deliberately reaching past the contract
                self._inner._principal_path(new_principal.builder_id), new_principal.to_dict()
            )
        return self._squatter


def test_a_store_that_leaves_an_orphaned_principal_is_refused(tmp_path):
    """The core does not merely avoid creating orphans itself — it refuses
    to report a login when the store left one behind, because "there is now
    an identity nobody can reach" is exactly the failure D11's race
    reasoning is about."""
    inner = _store(tmp_path)
    squatter = principal.resolve_verified_identity(inner, provider=GH, external_id="4242")
    store = _NonAtomicStore(inner, squatter.authenticator)

    with pytest.raises(principal.PrincipalError, match="orphaned identity"):
        principal.resolve_verified_identity(store, provider=GH, external_id="4242")


class _ForgetfulStore(_NonAtomicStore):
    def insert_authenticator(self, auth, *, new_principal=None):
        return self._inner.insert_authenticator(auth)  # drops the principal on the floor


def test_a_store_that_does_not_persist_the_principal_is_refused(tmp_path):
    inner = _store(tmp_path)
    store = _ForgetfulStore(inner, None)
    with pytest.raises(principal.PrincipalError, match="never minted"):
        # the inner store refuses the bind outright, which is the same
        # invariant seen from the other side: no principal, no binding
        principal.resolve_verified_identity(store, provider=GH, external_id="4242")


class _MissingReverseIndexStore(_OverwritingStore):
    def get_authenticator_for_builder(self, builder_id):
        return None  # pretends constraint 2 has nothing to enforce against


def test_a_store_without_a_reverse_index_is_refused(tmp_path):
    store = _MissingReverseIndexStore(_store(tmp_path))
    with pytest.raises(principal.PrincipalError, match="reverse index"):
        principal.resolve_verified_identity(store, provider=GH, external_id="4242")


class _WrongRowStore(_OverwritingStore):
    def get_authenticator(self, provider, external_id):
        rows = list(self.rows.values())
        return rows[0] if rows else None  # returns *a* row, not *the* row


def test_a_store_that_returns_the_wrong_row_is_refused(tmp_path):
    store = _WrongRowStore(_store(tmp_path))
    principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    with pytest.raises(principal.PrincipalError, match="when asked for"):
        principal.lookup_builder_id(store, provider=GH, external_id="9999")


# ── external_id must never do a builder_id's job (the D11 regression) ────────

def test_minted_builder_id_is_not_a_function_of_the_external_id(tmp_path):
    """The sharpest form of the D11 regression check: a derived id is a
    *function* of what GitHub returned, so it would be the same every time.
    Registering the identical external_id into 40 fresh stores must produce
    40 different builder_ids — any derivation scheme (the raw id, a hash of
    it, a prefix of it, an HMAC of it) fails this immediately."""
    minted = set()
    for i in range(40):
        store = principal.FilesystemPrincipalStore(tmp_path / f"store-{i}")
        minted.add(
            principal.resolve_verified_identity(store, provider=GH, external_id="4242").builder_id
        )
    assert len(minted) == 40


def test_minted_builder_id_does_not_carry_the_external_id(tmp_path):
    """And the direct form: a minted id must not be, contain, prefix, or
    suffix the GitHub account id. (Distinctive external_ids only — asserting
    that a 32-character hex string never contains the substring "1" is a
    test of arithmetic, not of this module.)"""
    store = _store(tmp_path)
    for external_id in ["4242424242", "99999999999", "totally-distinct-account", "7" * 40]:
        result = principal.resolve_verified_identity(store, provider=GH, external_id=external_id)
        b = result.builder_id
        assert b != external_id
        assert external_id not in b
        assert b != f"github-{external_id}"
        assert not b.endswith(external_id)
        assert not b.startswith(external_id)


def test_the_external_id_is_not_a_key_into_the_identity_namespace(tmp_path):
    """Give one account an `external_id` that is *literally another
    builder's* store-minted id. If anything anywhere treated external_id as
    a builder_id, this would resolve to the victim. It must mint a fresh,
    unrelated identity instead."""
    store = _store(tmp_path)
    victim = principal.resolve_verified_identity(store, provider=GH, external_id="4242")

    # nobody can reach the victim by *naming* their builder_id as an external id
    assert principal.lookup_builder_id(store, provider=GH, external_id=victim.builder_id) is None

    impostor = principal.resolve_verified_identity(store, provider=GH, external_id=victim.builder_id)
    assert impostor.builder_id != victim.builder_id
    assert impostor.created is True
    assert principal.lookup_builder_id(store, provider=GH, external_id="4242") == victim.builder_id
    assert store.get_authenticator_for_builder(victim.builder_id).external_id == "4242"


def test_the_external_id_never_becomes_a_path_component(tmp_path):
    """The 2026-08-01 audit rule, checked on disk rather than assumed: an
    identifier from someone else's namespace must not appear as a file or
    directory name anywhere under the store root."""
    store = _store(tmp_path)
    external_id = "totally-distinctive-external-id"
    result = principal.resolve_verified_identity(store, provider=GH, external_id=external_id)

    names = {p.name for p in (tmp_path / "principals").rglob("*")}
    assert not any(external_id in name for name in names), sorted(names)
    assert f"{result.builder_id}.json" in names  # the minted id is what keys the tree


def test_the_stored_row_still_records_which_github_account_it_was(tmp_path):
    """The flip side: GitHub is demoted to a capability provider, not
    erased. The binding row is what makes a later re-link or revocation
    possible at all."""
    store = _store(tmp_path)
    result = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    on_disk = json.loads(
        (tmp_path / "principals" / "by-builder" / f"{result.builder_id}.json").read_text()
    )
    assert on_disk["provider"] == GH
    assert on_disk["external_id"] == "4242"
    assert on_disk["builder_id"] == result.builder_id
    assert "linked_at" in on_disk

    # and the principal row itself holds nothing GitHub told us
    minted = json.loads(
        (tmp_path / "principals" / "principals" / f"{result.builder_id}.json").read_text()
    )
    assert set(minted) == {"builder_id", "minted_at"}


# ── input validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["../../etc/passwd", "", "a b", "a/b", ".hidden", "-lead", "x" * 300])
def test_bad_external_id_is_refused(tmp_path, bad):
    store = _store(tmp_path)
    with pytest.raises(principal.PrincipalError):
        principal.resolve_verified_identity(store, provider=GH, external_id=bad)
    with pytest.raises(principal.PrincipalError):
        principal.lookup_builder_id(store, provider=GH, external_id=bad)
    assert store.all_builder_ids() == []


@pytest.mark.parametrize("bad", ["../evil", "", "git hub", "gitlab", "GITHUB.COM", "x" * 300])
def test_bad_or_unregistered_provider_is_refused(tmp_path, bad):
    store = _store(tmp_path)
    with pytest.raises(principal.PrincipalError):
        principal.resolve_verified_identity(store, provider=bad, external_id="4242")
    assert store.all_builder_ids() == []


def test_a_traversing_external_id_writes_nothing_outside_the_root(tmp_path):
    store = _store(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    with pytest.raises(principal.PrincipalError):
        principal.resolve_verified_identity(store, provider=GH, external_id="../../../escape")
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    assert not (tmp_path.parent / "escape").exists()


def test_an_integer_external_id_is_refused_not_coerced(tmp_path):
    """GitHub's /user returns `id` as a JSON number. A caller that passed
    the int here and the str there would key one account two ways and mint
    it two identities — so the coercion is refused where it is visible."""
    store = _store(tmp_path)
    with pytest.raises(principal.PrincipalError, match="must be a str"):
        principal.resolve_verified_identity(store, provider=GH, external_id=4242)
    with pytest.raises(principal.PrincipalError, match="must be a str"):
        principal.lookup_builder_id(store, provider=GH, external_id=4242)


def test_a_non_string_builder_id_is_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(principal.PrincipalError, match="must be a str"):
        principal.bind_authenticator(store, provider=GH, external_id="1", builder_id=None)


@pytest.mark.parametrize("bad", ["../../etc/passwd", "", "a b", "a/b", ".hidden"])
def test_a_bad_builder_id_is_refused_at_the_bind_boundary(tmp_path, bad):
    store = _store(tmp_path)
    with pytest.raises(principal.PrincipalError, match="path-safety charset"):
        principal.bind_authenticator(store, provider=GH, external_id="1", builder_id=bad)


# ── store integrity ──────────────────────────────────────────────────────────

def test_store_refuses_a_symlinked_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(principal.PrincipalError, match="symlink"):
        principal.FilesystemPrincipalStore(link)


def test_corrupt_row_fails_closed_not_with_a_traceback(tmp_path):
    store = _store(tmp_path)
    result = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    path = tmp_path / "principals" / "principals" / f"{result.builder_id}.json"
    path.write_text("{not valid json")
    with pytest.raises(principal.PrincipalError, match="corrupt"):
        store.get_principal(result.builder_id)


def test_a_tampered_row_that_points_somewhere_else_is_refused(tmp_path):
    """The authenticator filename is a digest, so "a file exists here" is
    not the same fact as "this row is the one that was asked for". Rewriting
    a row's contents must be caught rather than answered."""
    store = _store(tmp_path)
    principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    auth_dir = tmp_path / "principals" / "authenticators"
    path = next(auth_dir.glob("*.json"))
    row = json.loads(path.read_text())
    row["external_id"] = "6666"  # same file, different claimed account
    path.write_text(json.dumps(row))
    with pytest.raises(principal.PrincipalError, match="inconsistent"):
        principal.lookup_builder_id(store, provider=GH, external_id="4242")


def test_a_principal_row_claiming_a_different_builder_id_is_refused(tmp_path):
    store = _store(tmp_path)
    result = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    path = tmp_path / "principals" / "principals" / f"{result.builder_id}.json"
    row = json.loads(path.read_text())
    row["builder_id"] = principal.mint_builder_id()
    path.write_text(json.dumps(row))
    with pytest.raises(principal.PrincipalError, match="inconsistent"):
        store.get_principal(result.builder_id)


def test_minting_over_an_existing_principal_is_refused(tmp_path):
    """Astronomically unlikely from a 128-bit generator, so it must fail
    closed rather than silently hand back an identity that is already
    someone else's."""
    store = _store(tmp_path)
    existing = principal.resolve_verified_identity(store, provider=GH, external_id="4242")
    auth = principal.Authenticator(
        provider=GH, external_id="6666", builder_id=existing.builder_id, linked_at=1.0
    )
    p = principal.Principal(builder_id=existing.builder_id, minted_at=1.0)
    winner = store.insert_authenticator(auth, new_principal=p)
    assert winner.external_id == "4242"  # constraint 2 blocks it before any write

    # and directly, past the reverse index: re-minting over a live principal
    orphan_auth = principal.Authenticator(
        provider=GH, external_id="6666", builder_id=existing.builder_id, linked_at=1.0
    )
    (tmp_path / "principals" / "by-builder" / f"{existing.builder_id}.json").unlink()
    with pytest.raises(principal.PrincipalError, match="already been minted"):
        store.insert_authenticator(orphan_auth, new_principal=p)


def test_crash_between_the_two_index_writes_fails_safe_not_open(tmp_path):
    """Found in review (2026-08-01), not in the original test suite:
    `insert_authenticator` writes the reverse index (by-builder) and the
    forward index (authenticators) as two separate files under one lock.
    flock closes the race between concurrent CALLERS; it says nothing about
    a process that dies mid-insert, between the two writes.

    Confirmed exploitable with the original write order (forward, then
    reverse): deleting the reverse-index file to simulate that crash point
    let a second, different external_id bind to the same builder_id with no
    error — two GitHub accounts silently sharing one identity. The fix
    reorders the writes (reverse, then forward) so the same crash instead
    leaves an orphaned reverse row that still blocks a second bind. This
    test simulates the crash under the CURRENT (safe) order and asserts
    both halves of what "safe" means: the second bind is refused, and the
    original identity can still recover on its next login (with a fresh
    builder_id, since its forward row is the one that's gone) rather than
    being permanently locked out.
    """
    store = _store(tmp_path)
    original = principal.resolve_verified_identity(store, provider=GH, external_id="111")
    builder_x = original.builder_id

    # Simulate a crash between the reverse-index write and the forward-index
    # write, under the current (reverse-first) order: the forward row is the
    # one that never landed.
    forward_row = store._auth_path(GH, "111")
    assert forward_row.exists()
    forward_row.unlink()

    # A second, different external identity must NOT be able to bind to the
    # now-inconsistent builder_id — the orphaned reverse row must still
    # block it, same as if the bind had succeeded cleanly.
    with pytest.raises(principal.AuthenticatorConflict, match="already has an authenticator"):
        principal.bind_authenticator(store, provider=GH, external_id="222", builder_id=builder_x)

    # And nothing can log in as builder_x's *original* identity anymore
    # (its forward row is gone) — but the original human is not locked out
    # of the system entirely: their next login mints a fresh identity rather
    # than erroring, because resolve_verified_identity's fast path correctly
    # reports "never seen" for a missing forward row.
    assert principal.lookup_builder_id(store, provider=GH, external_id="111") is None
    recovered = principal.resolve_verified_identity(store, provider=GH, external_id="111")
    assert recovered.created is True
    assert recovered.builder_id != builder_x  # a fresh identity, not the orphaned one


def test_insert_rejects_a_principal_that_disagrees_with_its_authenticator(tmp_path):
    store = _store(tmp_path)
    auth = principal.Authenticator(
        provider=GH, external_id="4242", builder_id=principal.mint_builder_id(), linked_at=1.0
    )
    mismatched = principal.Principal(builder_id=principal.mint_builder_id(), minted_at=1.0)
    with pytest.raises(principal.PrincipalError, match="does not match"):
        store.insert_authenticator(auth, new_principal=mismatched)


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_login_lookup_show(tmp_path, capsys):
    root = str(tmp_path / "principals")
    assert principal.main(["--root", root, "login", "--provider", "github", "--external-id", "4242"]) == 0
    builder_id = json.loads(capsys.readouterr().out)["builder_id"]

    assert principal.main(["--root", root, "lookup", "--provider", "github", "--external-id", "4242"]) == 0
    assert capsys.readouterr().out.strip() == builder_id

    assert principal.main(["--root", root, "show", builder_id]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["principal"]["builder_id"] == builder_id
    assert shown["authenticator"]["external_id"] == "4242"

    assert principal.main(["--root", root, "lookup", "--provider", "github", "--external-id", "1"]) == 1
    assert principal.main(["--root", root, "login", "--provider", "gitlab", "--external-id", "1"]) == 1
