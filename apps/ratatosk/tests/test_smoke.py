"""Launcher smoke tests — runtime comes from willow-ratatosk on PyPI."""

from importlib.metadata import version

from promotion_seam.capabilities import CapabilityGate, ActionResult
from promotion_seam.protocol.envelope import Intent, build_envelope


def test_willow_ratatosk_installed():
    assert version("willow-ratatosk").startswith("1.2")


def test_entry_point_importable():
    from ratatosk.crown import main

    assert callable(main)


def test_capability_gate_seam():
    gate = CapabilityGate()
    env = build_envelope(
        to="ratatosk",
        prompt="echo hi",
        intent=Intent.SHELL.value,
        requires_confirm=False,
    )
    assert gate.classify(env) == ActionResult.REJECTED
