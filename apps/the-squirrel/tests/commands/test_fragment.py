from responder.commands.fragment import parse_stash_args

def test_parse_text_only():
    r = parse_stash_args(["Oscar", "Mann", "Iowa", "1882"])
    assert "Oscar" in r["story_text"]
    assert r["confidence"] == "uncertain"

def test_parse_with_confidence():
    r = parse_stash_args(["Oscar", "Mann", "--confidence", "likely"])
    assert r["confidence"] == "likely"
    assert "Oscar Mann" in r["story_text"]

def test_parse_with_source():
    r = parse_stash_args(["Some", "text", "--source", "census"])
    assert r["source"] == "census"
