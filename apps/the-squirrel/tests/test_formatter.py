from responder.formatter import result_block, acorn_card, pedigree_chart

def test_result_block_contains_title():
    out = result_block("Test Title", "some content")
    assert "Test Title" in out
    assert "some content" in out

def test_result_block_has_separator():
    out = result_block("Heading", "body")
    assert "---" in out

def test_acorn_card_source_and_title():
    card = acorn_card("familysearch", "Oscar Mann record", "b. 1882 Iowa")
    assert "FAMILYSEARCH" in card
    assert "Oscar Mann record" in card

def test_acorn_card_with_url():
    card = acorn_card("findagrave", "Oscar Mann", "burial 1951", url="https://example.com")
    assert "https://example.com" in card

def test_pedigree_chart_contains_names():
    ancestors = {
        1: {"full_name": "Oscar Mann", "birth_date": "1882"},
        2: {"full_name": "Carl Mann", "birth_date": "1855"},
        3: {"full_name": "Anna Weber", "birth_date": "1858"},
    }
    chart = pedigree_chart("Oscar Mann", ancestors)
    assert "Oscar Mann" in chart
    assert "Carl Mann" in chart
    assert "Anna Weber" in chart
