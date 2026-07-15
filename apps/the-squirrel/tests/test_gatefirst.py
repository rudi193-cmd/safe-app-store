"""
Pins the gate-first slice (gatefirst/): capability handles, not call-site checks.

Deliberately independent of sap.core.gate — the conftest autouse actor fixture
sets a thread-local this package never reads, so it is inert here.
"""

import pytest

from gatefirst import app
from gatefirst.identity import Gatehouse, ReadHandle, StewardHandle, WriteHandle
from gatefirst.store import Denied, Store


@pytest.fixture
def house(tmp_path):
    return Gatehouse(base_dir=tmp_path / "gate", db_path=tmp_path / "squirrel.db")


def test_journal_can_add_read_export(house):
    journal = house.check_in("journal")
    assert isinstance(journal, StewardHandle)
    p = journal.add_person(full_name="Oscar Mann",
                           birth_date="1898", birth_place="Palmyra")
    f = journal.add_fragment(person_name="Oscar Mann",
                             story_text="Kept bees behind the barn.",
                             confidence="likely")
    linked = journal.link(f["id"], p["id"])
    assert linked["person_id"] == p["id"]
    assert journal.search_persons("Oscar")[0]["full_name"] == "Oscar Mann"
    ged = journal.export_gedcom_text()
    assert ged.startswith("0 HEAD")
    assert "1 NAME Oscar Mann" in ged and "2 PLAC Palmyra" in ged
    assert ged.rstrip().endswith("0 TRLR")


def test_jeles_reads_what_journal_wrote(house):
    journal = house.check_in("journal")
    p = journal.add_person(full_name="Ada Mann")
    jeles = house.check_in("jeles")
    assert jeles.search_persons("Ada")[0]["full_name"] == "Ada Mann"
    assert jeles.get_person(p["id"])["full_name"] == "Ada Mann"
    assert jeles.list_fragments() == []


def test_jeles_handle_has_no_write_surface(house):
    jeles = house.check_in("jeles")
    assert isinstance(jeles, ReadHandle)
    assert not isinstance(jeles, WriteHandle)
    for capability in ("add_person", "add_fragment", "link", "export_gedcom_text"):
        assert not hasattr(jeles, capability)


def test_jeles_export_denied_even_past_the_handle(house):
    jeles = house.check_in("jeles")
    assert not hasattr(jeles, "export_gedcom_text")
    # reach past the capability surface to the store: the gate still refuses
    with pytest.raises(Denied):
        jeles._store.export_gedcom_text()
    assert "BLOCKED export" in house.announcements


def test_jeles_write_denied_even_past_the_handle(house):
    jeles = house.check_in("jeles")
    with pytest.raises(Denied):
        jeles._store.add_person(full_name="Mallory")
    assert "BLOCKED tool=write" in house.announcements


def test_store_unreachable_without_session(house):
    with pytest.raises(Denied):
        Store(None, None)
    with pytest.raises(Denied):
        Store(house._gate, {"nonce": "0" * 32})  # forged: never checked in


def test_ledger_announces_tool_use_and_checkout(house):
    journal = house.check_in("journal")
    journal.add_person(full_name="Eve Mann")
    journal.search_persons("Eve")
    log = house.announcements
    assert "CHECK-IN Steady" in log
    assert "TOOL write" in log and "TOOL read" in log
    house.check_out(journal)
    assert "CHECK-OUT" in house.announcements


def test_app_commands_never_mention_auth(house):
    journal = house.check_in("journal")
    assert "planted" in app.run(journal, "add", "Oscar Mann", "1898")
    assert "Oscar Mann" in app.run(journal, "people", "Oscar")
    assert "stashed" in app.run(journal, "stash", "Oscar Mann", "Kept bees.")
    assert "0 TRLR" in app.run(journal, "export")
    jeles = house.check_in("jeles")
    assert "Oscar Mann" in app.run(jeles, "people")
    assert "not granted" in app.run(jeles, "add", "Mallory")
    assert "not granted" in app.run(jeles, "export")
