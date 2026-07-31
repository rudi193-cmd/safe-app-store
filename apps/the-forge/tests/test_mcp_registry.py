import pytest

from the_forge.mcp_registry import NESTOR_ALLOWED_TOOLS, McpRegistry, RegistryError


def test_registering_with_no_allowlist_is_refused():
    reg = McpRegistry()
    with pytest.raises(RegistryError, match="empty allowlist"):
        reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=[])


def test_registered_tool_is_allowed():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask"])
    assert reg.is_allowed("nestor", "nestor_ask")


def test_unregistered_tool_on_a_known_server_is_denied():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask"])
    assert not reg.is_allowed("nestor", "nestor_seal")  # withheld — never on the list


def test_unknown_server_is_denied():
    reg = McpRegistry()
    assert not reg.is_allowed("some-other-server", "anything")


def test_no_exact_match_no_prefix_or_wildcard_leniency():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask"])
    assert not reg.is_allowed("nestor", "nestor_as")
    assert not reg.is_allowed("nestor", "nestor_ask_extra")
    assert not reg.is_allowed("nestor", "nestor_")


def test_reregistration_is_refused_not_treated_as_an_update():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask"])
    with pytest.raises(RegistryError, match="already registered"):
        reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_propose"])


def test_deny_reason_distinguishes_unknown_server_from_unallowed_tool():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask"])
    assert "not registered" in reg.deny_reason("ghost-server", "anything")
    assert "not on server" in reg.deny_reason("nestor", "nestor_seal")


def test_allowed_tools_returns_the_frozenset():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask", "nestor_propose"])
    assert reg.allowed_tools("nestor") == frozenset({"nestor_ask", "nestor_propose"})


def test_allowed_tools_on_unregistered_server_raises():
    reg = McpRegistry()
    with pytest.raises(RegistryError):
        reg.allowed_tools("ghost-server")


def test_nestor_allowed_tools_constant_matches_the_design_docs_inventory():
    """docs/design/the-forge.md's "Nestor inventory" table lists these seven
    — nestor_seal is explicitly WITHHELD there and must never appear here."""
    assert NESTOR_ALLOWED_TOOLS == frozenset({
        "nestor_ask", "nestor_resolve", "nestor_check", "nestor_match",
        "nestor_provenance", "nestor_ledger_verify", "nestor_propose",
    })
    assert "nestor_seal" not in NESTOR_ALLOWED_TOOLS
    assert "nestor_unseal" not in NESTOR_ALLOWED_TOOLS
