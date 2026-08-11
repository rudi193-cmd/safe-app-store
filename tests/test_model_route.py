"""Tests for stores/model_route.py — D7-A: declared-not-ambient model routing.

Local (loopback vLLM) needs no permission and no network; cloud (off-machine)
is refused unless the build's manifest declares the cloud-fallback permission,
and only then does the run get `allow_net`. Pure/stdlib (via the vendored
model_egress detector) — no model, no network calls in the test; deterministic
by using literal IPs so is_local_host never hits real DNS. Written test-first.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("model_route", _REPO / "stores" / "model_route.py")
model_route = importlib.util.module_from_spec(_spec)
sys.modules["model_route"] = model_route
_spec.loader.exec_module(model_route)

_PERM = model_route.CLOUD_FALLBACK_PERMISSION
LOCAL = "http://127.0.0.1:11434"          # literal loopback — no DNS
OFF_MACHINE = "http://10.0.0.5:11434"     # literal non-loopback — no DNS


def _manifest(permissions):
    return {"app_id": "x", "permissions": list(permissions), "store_scope": [], "maker": "dev"}


# ── local: no permission, no net ─────────────────────────────────────────────

def test_loopback_host_routes_local_with_no_net_and_no_permission_needed():
    d = model_route.route(_manifest([]), model_host=LOCAL)
    assert d.target == "local"
    assert d.allow_net is False
    assert d.denial is None


# ── cloud: declared -> permitted, with net ───────────────────────────────────

def test_off_machine_host_with_the_declared_permission_routes_cloud_with_net():
    d = model_route.route(_manifest([_PERM]), model_host=OFF_MACHINE)
    assert d.target == "cloud"
    assert d.allow_net is True
    assert d.denial is None


# ── cloud: undeclared -> refused (declared, not ambient) ─────────────────────

def test_off_machine_host_without_the_permission_is_refused_and_gets_no_net():
    d = model_route.route(_manifest([]), model_host=OFF_MACHINE)
    assert d.target is None            # not routed anywhere
    assert d.allow_net is False        # never silently networked
    assert d.denial is not None
    # the denial names the missing permission and the host — trains toward
    # declaring it, not routing around the gate
    assert _PERM in d.denial["error"]
    assert OFF_MACHINE in d.denial["error"]


def test_a_local_permission_is_not_confused_with_cloud():
    # an unrelated declared permission does not grant cloud fallback
    d = model_route.route(_manifest(["write_files"]), model_host=OFF_MACHINE)
    assert d.target is None
    assert d.denial is not None


# ── fail-closed: anything not provably loopback is egress ────────────────────

def test_an_unresolvable_or_garbage_host_is_treated_as_egress_not_local():
    for host in ("http://nonexistent.invalid:11434", "not a url", "http://:/"):
        d = model_route.route(_manifest([]), model_host=host)
        # not provably loopback -> egress -> refused without the permission
        assert d.target is None, host
        assert d.allow_net is False, host
        assert d.denial is not None, host


def test_the_default_host_when_unset_is_local(monkeypatch):
    monkeypatch.delenv(model_route.model_egress.MODEL_HOST_ENV, raising=False)
    d = model_route.route(_manifest([]))  # no model_host -> DEFAULT (localhost)
    assert d.target == "local"
    assert d.allow_net is False


def test_env_host_is_used_when_no_explicit_host_is_passed(monkeypatch):
    monkeypatch.setenv(model_route.model_egress.MODEL_HOST_ENV, OFF_MACHINE)
    d = model_route.route(_manifest([]))  # reads env, off-machine, no perm -> refused
    assert d.denial is not None
    assert d.target is None


# ── permits() helper ─────────────────────────────────────────────────────────

def test_permits_reads_the_manifest_permission_list():
    assert model_route.permits(_manifest([_PERM])) is True
    assert model_route.permits(_manifest([])) is False
    assert model_route.permits({"app_id": "x"}) is False  # missing permissions key -> False


# ── scheme-less OLLAMA_HOST (the standard config) stays local ────────────────
# Regression for the audit's §3: a bare host:port / localhost must not read as
# off-machine (which would pressure cloud_llm_fallback on for a local build).

def test_scheme_less_loopback_hosts_route_local():
    for h in ("127.0.0.1:11434", "127.0.0.1", "localhost:11434", "localhost"):
        d = model_route.route(_manifest([]), model_host=h)
        assert d.target == "local", h
        assert d.allow_net is False, h
        assert d.denial is None, h


def test_scheme_less_off_machine_host_is_still_refused():
    d = model_route.route(_manifest([]), model_host="10.0.0.5:11434")
    assert d.target is None
    assert d.allow_net is False
    assert d.denial is not None


# ── loopback-confusion / SSRF forms fail in the safe direction ───────────────

def test_userinfo_splice_reads_the_real_host_not_the_loopback_prefix():
    # the connect target is 10.0.0.5; the 127.0.0.1 is only URL userinfo
    d = model_route.route(_manifest([]), model_host="http://127.0.0.1@10.0.0.5/")
    assert d.target is None       # refused — not fooled into "local"
    assert d.denial is not None


def test_zero_host_is_not_treated_as_loopback():
    d = model_route.route(_manifest([]), model_host="0.0.0.0:11434")
    assert d.target is None       # 0.0.0.0 is not loopback -> refuse (safe over-refusal)
    assert d.denial is not None
