from gedcom.exporter import build_gedcom_lines

def test_header_and_trailer():
    lines = build_gedcom_lines([], [])
    assert lines[0] == "0 HEAD"
    assert lines[-1] == "0 TRLR"

def test_person_in_output():
    persons = [{"id": 1, "full_name": "Oscar Mann", "birth_date": "1882",
                "birth_place": "Iowa", "death_date": "1951", "death_place": None,
                "burial_place": None}]
    lines = build_gedcom_lines(persons, [])
    text = "\n".join(lines)
    assert "INDI" in text
    assert "Oscar Mann" in text
    assert "1882" in text
    assert "Iowa" in text
