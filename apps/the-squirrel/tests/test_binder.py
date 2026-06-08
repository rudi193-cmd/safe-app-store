from binder import _name_similarity, Binder
from unittest.mock import MagicMock

def test_similarity_exact():
    assert _name_similarity("Oscar Mann", "Oscar Mann") == 1.0

def test_similarity_close():
    assert 0.7 < _name_similarity("Oscar Mann", "Oscar Man") < 1.0

def test_similarity_different():
    assert _name_similarity("Oscar Mann", "Carl Weber") < 0.5

def test_bind_updates_row():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.rowcount = 1
    b = Binder(mock_conn)
    result = b.bind(fragment_id=7, person_id=42)
    assert result["fragment_id"] == 7
    assert result["person_id"] == 42
    mock_conn.commit.assert_called()
