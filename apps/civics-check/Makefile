# civics-check app-local targets (run from apps/civics-check/)

.PHONY: run tui catalog

# Zero-dependency CLI (always works, no pip install needed)
run: catalog
	python3 app.py

# Textual dashboard (requires: pip install -r requirements-tui.txt)
tui: catalog
	@command -v ../../.venv-dev/bin/python >/dev/null 2>&1 && \
		../../.venv-dev/bin/python tui.py || python3 tui.py

catalog:
	python3 scripts/build_catalog.py
