"""Tests for stores/quota.py — per-builder fairness quotas (D6).

Same loading pattern as tests/test_session.py / tests/test_checkpoint_memory.py:
load the module directly from stores/, no package install. Every test builds
its own store root under tmp_path — nothing here ever touches the real
stores/.quotas.

The adversarial bar this file is written to, mirroring test_principal.py's
and test_session.py's own framing: it is not enough that the happy path
works. A naive read-then-write quota check has a classic check-then-increment
race; a crash-mid-build must not permanently steal a concurrency slot (nor
should "recoverable" quietly become "leases don't matter until manually
released"); a hostile builder_id must be rejected before any file is
touched; and cumulative sandbox-seconds must accumulate correctly and stay
isolated per builder. Each gets its own section below.
"""
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("quota", _REPO / "stores" / "quota.py")
quota = importlib.util.module_from_spec(_spec)
sys.modules["quota"] = quota
_spec.loader.exec_module(quota)

principal = quota.principal  # the same principal.py quota.py itself loaded

GOOD_BUILDER_ID = "a" * 32  # path-safe under principal.py's _check_builder_id
OTHER_BUILDER_ID = "b" * 32


def _store(tmp_path):
    return quota.FilesystemQuotaStore(tmp_path / "quotas")


# ── acquire / release round trip ─────────────────────────────────────────────

def test_acquire_then_release_frees_the_slot(tmp_path):
    store = _store(tmp_path)
    lease = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    assert lease.builder_id == GOOD_BUILDER_ID
    assert lease.lease_id
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 1

    quota.release_build_slot(store, lease)
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0
    # released slot is recoverable for a new build
    lease2 = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    assert lease2.lease_id != lease.lease_id


def test_lease_release_method_is_equivalent_to_the_free_function(tmp_path):
    store = _store(tmp_path)
    lease = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    lease.release()
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0


def test_release_is_idempotent(tmp_path):
    store = _store(tmp_path)
    lease = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    quota.release_build_slot(store, lease)
    quota.release_build_slot(store, lease)  # must not raise
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0


def test_releasing_an_unknown_lease_is_a_silent_no_op(tmp_path):
    store = _store(tmp_path)
    fake = quota.BuildLease(
        lease_id="never-issued", builder_id=GOOD_BUILDER_ID,
        acquired_at=0.0, expires_at=0.0, _store=store,
    )
    quota.release_build_slot(store, fake)  # must not raise
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0


def test_releasing_one_lease_does_not_affect_a_sibling_lease(tmp_path):
    store = _store(tmp_path)
    first = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=5)
    second = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=5)
    quota.release_build_slot(store, first)
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 1
    quota.release_build_slot(store, second)
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0


# ── concurrency limit, enforced fail-closed ──────────────────────────────────

def test_a_third_acquire_over_the_limit_is_refused(tmp_path):
    store = _store(tmp_path)
    quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=2)
    quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=2)
    with pytest.raises(quota.QuotaExceededError) as ei:
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=2)
    assert ei.value.reason == "concurrency"
    assert ei.value.active_concurrent == 2
    assert ei.value.max_concurrent == 2
    assert ei.value.builder_id == GOOD_BUILDER_ID


def test_max_concurrent_is_overridable_per_call_not_a_single_global(tmp_path):
    store = _store(tmp_path)
    # a builder-tier of 1 refuses a second build...
    quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    with pytest.raises(quota.QuotaExceededError):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    # ...while a different builder with a higher override is unaffected
    quota.acquire_build_slot(store, OTHER_BUILDER_ID, max_concurrent=4)
    quota.acquire_build_slot(store, OTHER_BUILDER_ID, max_concurrent=4)
    assert quota.active_build_count(store, OTHER_BUILDER_ID) == 2


def test_default_max_concurrent_applies_when_not_overridden(tmp_path):
    store = _store(tmp_path)
    for _ in range(quota.DEFAULT_MAX_CONCURRENT_BUILDS):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID)
    with pytest.raises(quota.QuotaExceededError):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID)


def test_two_different_builders_do_not_share_a_concurrency_limit(tmp_path):
    store = _store(tmp_path)
    quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=1)
    # a different builder's own limit is untouched by the first builder's usage
    lease = quota.acquire_build_slot(store, OTHER_BUILDER_ID, max_concurrent=1)
    assert lease.builder_id == OTHER_BUILDER_ID


def test_acquire_rejects_a_non_positive_max_concurrent(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError, match="max_concurrent"):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=0)
    with pytest.raises(quota.QuotaError, match="max_concurrent"):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=-1)
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0


def test_acquire_rejects_a_non_positive_lease_ttl(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError, match="lease_ttl_seconds"):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, lease_ttl_seconds=0)
    with pytest.raises(quota.QuotaError, match="lease_ttl_seconds"):
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, lease_ttl_seconds=-5)
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == 0


# ── crash recovery / TTL expiry ──────────────────────────────────────────────

def test_an_expired_lease_does_not_count_against_the_limit(tmp_path):
    """The orphaned-lease recovery case: a lease minted, never released, its
    TTL elapses — a subsequent acquire for the same builder must succeed,
    treating the slot as free again."""
    store = _store(tmp_path)
    quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=10, now=1_000_000.0
    )
    # well past expiry, and never released
    lease2 = quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=10, now=1_000_020.0
    )
    assert lease2.builder_id == GOOD_BUILDER_ID
    # exactly one lease is now on record as active (the expired one aged out)
    assert quota.active_build_count(store, GOOD_BUILDER_ID, now=1_000_020.0) == 1


def test_a_not_yet_expired_lease_still_counts_against_the_limit(tmp_path):
    """The other half of the same invariant: "abandoned recovery" must not
    accidentally become "leases don't matter until manually released" — a
    lease well within its TTL still blocks a new acquire at the limit."""
    store = _store(tmp_path)
    quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=600, now=1_000_000.0
    )
    with pytest.raises(quota.QuotaExceededError):
        quota.acquire_build_slot(
            store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=600, now=1_000_060.0
        )


def test_expiry_is_a_half_open_window_exactly_at_expires_at_is_expired(tmp_path):
    store = _store(tmp_path)
    quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=100, now=1_000_000.0
    )
    # at t=1_000_099 (1s before expiry) the lease still counts
    with pytest.raises(quota.QuotaExceededError):
        quota.acquire_build_slot(
            store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=100, now=1_000_099.0
        )
    # at t=1_000_100 (exactly expires_at) it no longer does
    lease2 = quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=100, now=1_000_100.0
    )
    assert lease2 is not None


def test_default_lease_ttl_exceeds_sandbox_runners_default_timeout():
    """D6's own requirement: the lease must outlive the build it represents
    under normal conditions, or a slow-but-healthy build (one that
    legitimately runs close to sandbox_runner's own DEFAULT_TIMEOUT_S)
    would get treated as abandoned while still running.

    `the_forge` is not pip-installed in this environment (see
    apps/the-forge/tests' own honest-environment notes). `sandbox_runner.py`
    does a real intra-package relative import (`from .plan import ...`), so
    unlike principal.py's standalone-script loading this needs its actual
    package context — putting `apps/the-forge/src` on `sys.path` and
    importing normally, rather than skipped, so this actually checks the
    real constant instead of trusting a copied-down number."""
    forge_src = str(_REPO / "apps" / "the-forge" / "src")
    added = forge_src not in sys.path
    if added:
        sys.path.insert(0, forge_src)
    try:
        from the_forge import sandbox_runner as forge_runner
    finally:
        if added:
            sys.path.remove(forge_src)
    assert quota.DEFAULT_LEASE_TTL_SECONDS > forge_runner.DEFAULT_TIMEOUT_S


def test_release_of_an_already_expired_lease_is_still_a_silent_no_op(tmp_path):
    store = _store(tmp_path)
    lease = quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=1, lease_ttl_seconds=10, now=1_000_000.0
    )
    quota.release_build_slot(store, lease, now=1_000_020.0)  # must not raise
    assert quota.active_build_count(store, GOOD_BUILDER_ID, now=1_000_020.0) == 0


# ── the check-then-increment race ────────────────────────────────────────────

def test_concurrent_acquires_never_exceed_max_concurrent(tmp_path):
    """The bug class this module exists to make impossible: many callers
    racing for the same builder's last available slot. Exactly
    max_concurrent may succeed; every other caller must see
    QuotaExceededError, never a silent over-grant."""
    store = _store(tmp_path)
    max_concurrent = 4
    parties = 32
    results = [None] * parties
    errors = [None] * parties

    def worker(i):
        try:
            results[i] = quota.acquire_build_slot(
                store, GOOD_BUILDER_ID, max_concurrent=max_concurrent
            )
        except quota.QuotaExceededError as e:
            errors[i] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(parties)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    granted = [r for r in results if r is not None]
    refused = [e for e in errors if e is not None]
    assert len(granted) == max_concurrent, f"expected exactly {max_concurrent} grants, got {len(granted)}"
    assert len(refused) == parties - max_concurrent
    # every grant is a genuinely distinct lease
    assert len({l.lease_id for l in granted}) == max_concurrent
    # the store agrees with what was handed out
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == max_concurrent


def test_concurrent_acquire_and_release_settle_correctly(tmp_path):
    """A tighter race: acquire up to the limit, then hammer concurrent
    acquire attempts WHILE a release is in flight — at no point should the
    active count exceed max_concurrent, and the store must end up
    consistent."""
    store = _store(tmp_path)
    max_concurrent = 3
    held = [
        quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=max_concurrent)
        for _ in range(max_concurrent)
    ]
    assert quota.active_build_count(store, GOOD_BUILDER_ID) == max_concurrent

    errors = []

    def releaser():
        quota.release_build_slot(store, held[0])

    def acquirer(out, i):
        try:
            out[i] = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=max_concurrent)
        except quota.QuotaExceededError:
            out[i] = None
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    results = [None] * 8
    threads = [threading.Thread(target=acquirer, args=(results, i)) for i in range(8)]
    threads.append(threading.Thread(target=releaser))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    granted = [r for r in results if r is not None]
    # at most one acquirer could have won the single freed slot
    assert len(granted) <= 1
    assert quota.active_build_count(store, GOOD_BUILDER_ID) <= max_concurrent


# ── malformed / hostile builder_id ───────────────────────────────────────────

@pytest.mark.parametrize("bad", ["../../etc/passwd", "", "a b", "a/b", ".hidden", "-lead"])
def test_acquire_refuses_a_builder_id_that_fails_principals_own_charset_check(tmp_path, bad):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError):
        quota.acquire_build_slot(store, bad)
    # no file left behind for the hostile input
    assert store.all_builder_ids() == []
    with pytest.raises(principal.PrincipalError):
        principal._check_builder_id(bad)


def test_acquire_refuses_a_non_string_builder_id(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError):
        quota.acquire_build_slot(store, None)
    with pytest.raises(quota.QuotaError):
        quota.acquire_build_slot(store, 4242)
    assert store.all_builder_ids() == []


def test_record_duration_refuses_a_hostile_builder_id_before_touching_disk(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError):
        quota.record_build_duration(store, "../escape", 5.0)
    assert store.all_builder_ids() == []


def test_sandbox_seconds_used_refuses_a_hostile_builder_id(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError):
        quota.sandbox_seconds_used(store, "../escape")
    assert store.all_builder_ids() == []


def test_no_file_created_for_a_symlinked_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(quota.QuotaError, match="symlink"):
        quota.FilesystemQuotaStore(link)


# ── sandbox-seconds accounting ───────────────────────────────────────────────

def test_record_build_duration_accumulates_across_multiple_calls(tmp_path):
    store = _store(tmp_path)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 10.0)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 25.5)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 4.5)
    assert quota.sandbox_seconds_used(store, GOOD_BUILDER_ID) == pytest.approx(40.0)


def test_sandbox_seconds_used_is_per_builder_isolated(tmp_path):
    store = _store(tmp_path)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 100.0)
    quota.record_build_duration(store, OTHER_BUILDER_ID, 3.0)
    assert quota.sandbox_seconds_used(store, GOOD_BUILDER_ID) == pytest.approx(100.0)
    assert quota.sandbox_seconds_used(store, OTHER_BUILDER_ID) == pytest.approx(3.0)


def test_rolling_window_excludes_records_older_than_the_window(tmp_path):
    store = _store(tmp_path)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 50.0, now=1_000_000.0)  # old
    quota.record_build_duration(store, GOOD_BUILDER_ID, 7.0, now=1_000_500.0)   # recent
    # running total sees both
    assert quota.sandbox_seconds_used(store, GOOD_BUILDER_ID, now=1_000_500.0) == pytest.approx(57.0)
    # a 100s window from now=1_000_500 only catches the recent record
    used = quota.sandbox_seconds_used(
        store, GOOD_BUILDER_ID, window_seconds=100.0, now=1_000_500.0
    )
    assert used == pytest.approx(7.0)


def test_record_build_duration_rejects_a_negative_duration(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(quota.QuotaError, match="elapsed_seconds"):
        quota.record_build_duration(store, GOOD_BUILDER_ID, -1.0)
    assert quota.sandbox_seconds_used(store, GOOD_BUILDER_ID) == 0.0


def test_sandbox_seconds_budget_blocks_further_acquires_once_reached(tmp_path):
    store = _store(tmp_path)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 100.0)
    with pytest.raises(quota.QuotaExceededError) as ei:
        quota.acquire_build_slot(
            store, GOOD_BUILDER_ID, max_concurrent=5, sandbox_seconds_budget=100.0
        )
    assert ei.value.reason == "budget"
    assert ei.value.sandbox_seconds_used == pytest.approx(100.0)
    assert ei.value.sandbox_seconds_budget == pytest.approx(100.0)


def test_sandbox_seconds_budget_does_not_apply_when_not_configured(tmp_path):
    store = _store(tmp_path)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 10_000.0)  # huge, but no budget passed
    lease = quota.acquire_build_slot(store, GOOD_BUILDER_ID, max_concurrent=5)
    assert lease is not None


def test_sandbox_seconds_budget_under_the_limit_still_allows_acquire(tmp_path):
    store = _store(tmp_path)
    quota.record_build_duration(store, GOOD_BUILDER_ID, 5.0)
    lease = quota.acquire_build_slot(
        store, GOOD_BUILDER_ID, max_concurrent=5, sandbox_seconds_budget=100.0
    )
    assert lease is not None


# ── store integrity ──────────────────────────────────────────────────────────

def test_corrupt_row_fails_closed_not_with_a_traceback(tmp_path):
    store = _store(tmp_path)
    quota.acquire_build_slot(store, GOOD_BUILDER_ID)
    path = store._row_path(GOOD_BUILDER_ID)
    path.write_text("{not valid json")
    with pytest.raises(quota.QuotaError, match="corrupt"):
        quota.active_build_count(store, GOOD_BUILDER_ID)


def test_a_row_claiming_a_different_builder_id_is_refused(tmp_path):
    store = _store(tmp_path)
    quota.acquire_build_slot(store, GOOD_BUILDER_ID)
    path = store._row_path(GOOD_BUILDER_ID)
    row = __import__("json").loads(path.read_text())
    row["builder_id"] = OTHER_BUILDER_ID
    path.write_text(__import__("json").dumps(row))
    with pytest.raises(quota.QuotaError, match="inconsistent"):
        quota.active_build_count(store, GOOD_BUILDER_ID)


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_acquire_record_used_release(tmp_path, capsys):
    import json as _json

    root = str(tmp_path / "quotas")
    assert quota.main(["--root", root, "acquire", GOOD_BUILDER_ID, "--max-concurrent", "1"]) == 0
    lease_id = _json.loads(capsys.readouterr().out)["lease_id"]

    assert quota.main(["--root", root, "acquire", GOOD_BUILDER_ID, "--max-concurrent", "1"]) == 1
    capsys.readouterr()

    assert quota.main(["--root", root, "record", GOOD_BUILDER_ID, "12.5"]) == 0
    capsys.readouterr()

    assert quota.main(["--root", root, "used", GOOD_BUILDER_ID]) == 0
    used = _json.loads(capsys.readouterr().out)["sandbox_seconds_used"]
    assert used == pytest.approx(12.5)

    assert quota.main(["--root", root, "release", GOOD_BUILDER_ID, lease_id]) == 0
    capsys.readouterr()

    assert quota.main(["--root", root, "acquire", GOOD_BUILDER_ID, "--max-concurrent", "1"]) == 0

    assert quota.main(["--root", root, "acquire", "../bad"]) == 1
