"""Tests for the shared willow_read seam (box audit A5)."""
import willow_read as wr


class FakeClient:
    def __init__(self, atoms):
        self.atoms = atoms
        self.calls = []

    def knowledge_search(self, query, limit):
        self.calls.append((query, limit))
        return self.atoms


class BoomClient:
    def knowledge_search(self, query, limit):
        raise RuntimeError("kb down")


def setup_function(_):
    wr.set_client(None)


def teardown_function(_):
    wr.set_client(None)


def test_no_client_returns_empty_and_no_backend():
    assert wr.active_backend() == "none"
    assert wr.available() is False
    assert wr.search("q") == []


def test_injected_client_is_used_and_scopes_the_read():
    atoms = [{"content": "a"}, {"content": "b"}]
    fake = FakeClient(atoms)
    wr.set_client(fake)
    assert wr.active_backend() == "mcp" and wr.available() is True
    assert wr.search("q", 10) == atoms
    assert fake.calls == [("q", 10)]     # the gated tool did the read, scoped


def test_client_arg_beats_module_level():
    wr.set_client(FakeClient([{"content": "module"}]))
    assert wr.search("q", client=FakeClient([{"content": "arg"}])) == [{"content": "arg"}]


def test_non_dict_atoms_are_filtered():
    wr.set_client(FakeClient([{"content": "ok"}, "junk", 42, None]))
    assert wr.search("q") == [{"content": "ok"}]


def test_raising_client_degrades_to_empty():
    wr.set_client(BoomClient())
    assert wr.search("q") == []          # never propagates
