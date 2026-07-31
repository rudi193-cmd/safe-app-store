from the_forge.cli import main


def test_status_exits_zero(capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "design-phase scaffold" in out
    assert "docs/design/the-forge.md" in out


def test_no_subcommand_is_a_usage_error():
    import pytest

    with pytest.raises(SystemExit):
        main([])
