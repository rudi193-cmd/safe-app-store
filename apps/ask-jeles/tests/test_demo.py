"""Offline demo deck."""

from askjeles.crown import _DEMO_PAYLOAD, _DEMO_QUERY


def test_demo_payload_shape():
    assert _DEMO_PAYLOAD["query"] == _DEMO_QUERY
    assert len(_DEMO_PAYLOAD["hits"]) >= 3
    assert _DEMO_PAYLOAD["query_class"] == "general"
    for hit in _DEMO_PAYLOAD["hits"]:
        assert hit.get("title")
        assert hit.get("snippet")
