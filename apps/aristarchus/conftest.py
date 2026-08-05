"""Make the src-layout package importable without an install.

The store-ci app-tests matrix installs each app's requirements.txt from the
REPO ROOT, and pip resolves a relative ``-e .`` against its own cwd, not the
requirements file - so ``-e .`` in this app's requirements tried to install
the repo root (no pyproject there) and failed the leg. Rather than encode
pip's cwd semantics into the requirements file, the tests stop needing an
install at all: pytest always loads the app-root conftest, and the package
imports from src/ wherever the run started. ``pip install -e .`` still works
for humans who want the ``aristarchus`` CLI on PATH.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
