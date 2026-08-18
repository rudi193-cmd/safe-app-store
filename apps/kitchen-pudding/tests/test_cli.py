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


def test_correct_through_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "pud-1", "--title", "Test", "--ingredient", "milk:2:cups:assumed"])
    capsys.readouterr()

    rc = main(["correct", "pud-1", "0", "provenance", "measured", "--note", "verified"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "correction recorded" in out

    rc = main(["show", "pud-1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "measured" in out
    assert "1 correction(s) on record" in out


def test_correct_unknown_recipe_through_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["correct", "ghost", "0", "qty", "3"])
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_show_unknown_recipe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["show", "ghost"])
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_list_empty_store(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["list"])
    assert rc == 0
    assert "no recipes" in capsys.readouterr().out.lower()


def test_add_with_note_in_ingredient(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main([
        "add", "pud-2", "--title", "Noted",
        "--ingredient", "flour:2:cups:fitted:from a video",
    ])
    assert rc == 0

    rc = main(["show", "pud-2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "from a video" in out


def test_add_with_tags(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main([
        "add", "pud-3", "--title", "Tagged",
        "--ingredient", "milk:1:cup:measured",
        "--tag", "dessert", "--tag", "quick",
    ])
    assert rc == 0

    rc = main(["show", "pud-3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dessert" in out
    assert "quick" in out


def test_search_by_title(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "cake-1", "--title", "Chocolate Cake",
          "--ingredient", "flour:2:cups:measured"])
    main(["add", "bread-1", "--title", "Bread",
          "--ingredient", "flour:3:cups:measured"])
    capsys.readouterr()

    rc = main(["search", "--title", "chocolate"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "cake-1" in out
    assert "bread-1" not in out


def test_search_by_ingredient(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "r1", "--title", "A", "--ingredient", "flour:2:cups:measured"])
    main(["add", "r2", "--title", "B", "--ingredient", "sugar:1:tbsp:measured"])
    capsys.readouterr()

    rc = main(["search", "--ingredient-name", "sugar"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "r2" in out
    assert "r1" not in out


def test_search_no_results(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["search", "--title", "nonexistent"])
    assert rc == 0
    assert "no matching" in capsys.readouterr().out.lower()


def test_export_text(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "exp-1", "--title", "Export Test",
          "--ingredient", "flour:2:cups:measured",
          "--step", "mix it"])
    capsys.readouterr()

    rc = main(["export", "exp-1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Export Test" in out
    assert "2 cups flour" in out
    assert "1. mix it" in out


def test_export_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "exp-2", "--title", "JSON Export",
          "--ingredient", "flour:2:cups:measured"])
    capsys.readouterr()

    rc = main(["export", "exp-2", "--format", "json"])
    assert rc == 0
    import json
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "exp-2"


def test_export_to_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "exp-3", "--title", "File Export",
          "--ingredient", "flour:2:cups:measured"])
    capsys.readouterr()

    out_path = str(tmp_path / "out.txt")
    rc = main(["export", "exp-3", "--output", out_path])
    assert rc == 0
    content = (tmp_path / "out.txt").read_text()
    assert "File Export" in content


def test_export_unknown_recipe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["export", "ghost"])
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_import_from_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    import json
    recipe = {
        "id": "imp-1", "title": "Imported",
        "ingredients": [{"name": "flour", "qty": "2", "unit": "cups", "provenance": "measured"}],
    }
    f = tmp_path / "import-me.json"
    f.write_text(json.dumps(recipe))

    rc = main(["import", str(f)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "imported" in out.lower()

    rc = main(["show", "imp-1"])
    assert rc == 0
    assert "Imported" in capsys.readouterr().out


def test_import_missing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["import", "/nonexistent/recipe.json"])
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_import_duplicate_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    import json
    recipe = {
        "id": "dup-1", "title": "First",
        "ingredients": [{"name": "x", "qty": "1", "unit": "g", "provenance": "measured"}],
    }
    f = tmp_path / "dup.json"
    f.write_text(json.dumps(recipe))

    main(["import", str(f)])
    capsys.readouterr()
    rc = main(["import", str(f)])
    assert rc == 1


def test_tags_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "t1", "--title", "A",
          "--ingredient", "x:1:g:measured",
          "--tag", "bread", "--tag", "quick"])
    main(["add", "t2", "--title", "B",
          "--ingredient", "y:1:g:measured",
          "--tag", "dessert"])
    capsys.readouterr()

    rc = main(["tags"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "bread" in out
    assert "dessert" in out
    assert "quick" in out


def test_tags_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    rc = main(["tags"])
    assert rc == 0
    assert "no tags" in capsys.readouterr().out.lower()


def test_search_by_tag_through_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("APP_DATA", raising=False)

    main(["add", "tagged-1", "--title", "Tagged",
          "--ingredient", "x:1:g:measured",
          "--tag", "special"])
    main(["add", "untagged-1", "--title", "Plain",
          "--ingredient", "y:1:g:measured"])
    capsys.readouterr()

    rc = main(["search", "--tag-filter", "special"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tagged-1" in out
    assert "untagged-1" not in out
