"""
Isolate story-timeline tests from other apps (e.g. the-squirrel) that have
modules with the same names (migrate, safe_integration).

An autouse fixture runs before each test — clears conflicting sys.modules
entries and ensures apps/story-timeline is first on sys.path.
"""
import sys
import pytest
from pathlib import Path

_APP_PATH = str(Path(__file__).parents[2] / "apps" / "story-timeline")
_CONFLICT_MODULES = {
    "migrate",
    "safe_integration",
    "timeline_db",
    "willow_edges",
    "story_protocol",
    "soil_protocol",
    "promote",
    "mcp_client",
    "suggestion_store",
    "intelligence",
    "app",
    "import_csv",
}


@pytest.fixture(autouse=True)
def _isolate_story_timeline_modules():
    if _APP_PATH not in sys.path:
        sys.path.insert(0, _APP_PATH)
    else:
        sys.path.remove(_APP_PATH)
        sys.path.insert(0, _APP_PATH)
    for name in _CONFLICT_MODULES:
        sys.modules.pop(name, None)
    yield
