from responder.commands.relationship import parse_link_args

def test_parse_arrow_unicode():
    result = parse_link_args(["Oscar", "Mann", "→", "parent", "→", "Carl", "Mann"])
    assert result is not None
    a, rel, b = result
    assert a == "Oscar Mann"
    assert rel == "parent"
    assert b == "Carl Mann"

def test_parse_arrow_ascii():
    result = parse_link_args(["Oscar", "Mann", "->", "spouse", "->", "Mabel", "Jones"])
    assert result is not None
    a, rel, b = result
    assert rel == "spouse"
    assert b == "Mabel Jones"

def test_parse_no_arrow_returns_none():
    assert parse_link_args(["Oscar", "Mann", "parent", "Carl", "Mann"]) is None

def test_parse_missing_parts_returns_none():
    assert parse_link_args(["→", "parent", "→"]) is None
