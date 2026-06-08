from responder.commands.tree import render_pedigree

def test_render_pedigree_three_gen():
    ancestors = {
        1: {"full_name": "Oscar Mann", "birth_date": "1882"},
        2: {"full_name": "Carl Mann", "birth_date": "1855"},
        3: {"full_name": "Anna Weber", "birth_date": "1858"},
    }
    out = render_pedigree("Oscar Mann", ancestors)
    assert "Oscar Mann" in out
    assert "Carl Mann" in out
    assert "Anna Weber" in out
    assert "┌" in out

def test_render_pedigree_no_parents():
    ancestors = {1: {"full_name": "Oscar Mann", "birth_date": "1882"}}
    out = render_pedigree("Oscar Mann", ancestors)
    assert "Oscar Mann" in out

def test_render_pedigree_four_gen():
    ancestors = {
        1: {"full_name": "Oscar Mann", "birth_date": "1882"},
        2: {"full_name": "Carl Mann", "birth_date": "1855"},
        3: {"full_name": "Anna Weber", "birth_date": "1858"},
        4: {"full_name": "Johann Mann", "birth_date": "1820"},
        5: {"full_name": "Greta Braun", "birth_date": "1825"},
    }
    out = render_pedigree("Oscar Mann", ancestors)
    assert "Johann Mann" in out
    assert "Greta Braun" in out
