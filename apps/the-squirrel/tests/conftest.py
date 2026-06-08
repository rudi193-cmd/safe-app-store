"""
Inject a fake user_lattice module before any db.* import fires.
db/__init__.py does sys.path.insert(0, WILLOW_CORE) + from user_lattice import ...
We pre-populate sys.modules so it never hits the filesystem.
"""
import sys
import os
from types import ModuleType

_fake = ModuleType("user_lattice")
_fake.DOMAINS = frozenset({"biography", "geography", "genealogy", "culture", "migration"})
_fake.TEMPORAL_STATES = frozenset({"past", "present", "future", "unknown"})
_fake.DEPTH_MIN = 1
_fake.DEPTH_MAX = 23
_fake.LATTICE_SIZE = 23
sys.modules["user_lattice"] = _fake

os.environ.setdefault("WILLOW_CORE", "/tmp/fake_willow_core")
os.environ.setdefault("WILLOW_PG_DB", "willow")
os.environ.setdefault("SAP_AUTHORIZED", "1")
