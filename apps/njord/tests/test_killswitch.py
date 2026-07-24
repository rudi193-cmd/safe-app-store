"""engage() -> is_killed() True; the dead-man's-file is detected across instances."""
from njord.risk.killswitch import KillSwitch
from njord.paths import killswitch_path


def test_engage_sets_killed():
    ks = KillSwitch()
    assert ks.is_killed() is False
    ks.engage(reason="test")
    assert ks.is_killed() is True
    assert ks.path.exists()


def test_dead_mans_file_detected_by_fresh_instance():
    ks1 = KillSwitch()
    ks1.engage(reason="loop-detected-problem")
    # A brand-new instance (e.g. after restart) sees the file and stays killed.
    ks2 = KillSwitch()
    assert ks2.is_killed() is True


def test_disengage_clears_file():
    ks = KillSwitch()
    ks.engage()
    assert ks.is_killed()
    ks.disengage()
    assert ks.is_killed() is False
    assert not ks.path.exists()


def test_status_reports_path():
    ks = KillSwitch()
    st = ks.status()
    assert st["dead_mans_file"] == str(killswitch_path())
    assert st["killed"] is False
