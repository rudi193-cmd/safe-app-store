from __future__ import annotations

from kitchen_pudding.cli import main
from kitchen_pudding.store import RecipeStore


def test_no_args_prints_help_and_exits_zero(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_add_list_show_round_trip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    assert main([
        "add", "pud-1", "--title", "Test Pudding",
        "--ingredient", "milk:2:cups:measured",
        "--ingredient", "vanilla:1:tsp:assumed:guessed from a photo",
        "--step", "heat milk",
    ]) == 0
    capsys.readouterr()

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "pud-1" in out
    assert "assumed" in out  # weakest ingredient, so recipe-level provenance

    assert main(["show", "pud-1"]) == 0
    out = capsys.readouterr().out
    assert "Test Pudding" in out
    assert "heat milk" in out


def test_add_duplicate_id_fails_without_touching_original(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "pud-1", "--title", "First", "--ingredient", "milk:2:cups:measured"])
    capsys.readouterr()
    rc = main(["add", "pud-1", "--title", "Second", "--ingredient", "milk:3:cups:measured"])
    assert rc == 1
    assert RecipeStore().get_original("pud-1").title == "First"
