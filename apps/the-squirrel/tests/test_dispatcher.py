import pytest
from responder.dispatcher import parse_command, Command

def test_parse_add_person():
    cmd = parse_command("@squirrel: add person Oscar Mann b.1882 d.1951 p.Iowa")
    assert cmd is not None
    assert cmd.name == "add person"
    assert "Oscar" in cmd.args

def test_parse_tree():
    cmd = parse_command("@squirrel: tree Oscar Mann")
    assert cmd is not None
    assert cmd.name == "tree"
    assert cmd.args == ["Oscar", "Mann"]

def test_parse_link():
    cmd = parse_command("@squirrel: link Oscar Mann → parent → Carl Mann")
    assert cmd is not None
    assert cmd.name == "link"

def test_parse_mode():
    cmd = parse_command("@squirrel: mode chat")
    assert cmd.name == "mode"
    assert cmd.args == ["chat"]

def test_parse_status():
    cmd = parse_command("@squirrel: status")
    assert cmd.name == "status"
    assert cmd.args == []

def test_not_a_command():
    assert parse_command("Oscar Mann was born in Iowa") is None
    assert parse_command("") is None

def test_case_insensitive():
    cmd = parse_command("@Squirrel: TREE Oscar Mann")
    assert cmd is not None
    assert cmd.name == "tree"
