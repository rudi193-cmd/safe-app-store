from responder.commands.person import parse_person_args

def test_parse_full():
    r = parse_person_args("Oscar Mann b.1882 d.1951 p.Iowa".split())
    assert r["full_name"] == "Oscar Mann"
    assert r["birth_date"] == "1882"
    assert r["death_date"] == "1951"
    assert r["birth_place"] == "Iowa"

def test_parse_name_only():
    r = parse_person_args(["Oscar", "Mann"])
    assert r["full_name"] == "Oscar Mann"
    assert r.get("birth_date") is None

def test_parse_multiword_place():
    r = parse_person_args("Carl Mann b.1855 p.Dubuque_County_Iowa".split())
    assert r["birth_place"] == "Dubuque County Iowa"

def test_parse_no_name():
    r = parse_person_args(["b.1882"])
    assert r["full_name"] == ""
    assert r["birth_date"] == "1882"
