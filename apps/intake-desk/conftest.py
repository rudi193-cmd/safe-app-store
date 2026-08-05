import sys
from pathlib import Path

# The app's modules are top-level in this directory (the store's flat layout,
# as in field-notes and the-binder), so the app root has to be importable when
# pytest is run from here.
sys.path.insert(0, str(Path(__file__).parent))
