# civics-check app-local targets (run from apps/civics-check/)

.PHONY: run tui cli catalog test dev install

# Default: fair TUI (same as dev.sh without venv bootstrap)
run: catalog tui

# Zero-dependency CLI menu
cli: catalog
	python3 app.py --cli

# Textual fair
tui: catalog
	@command -v ../../.venv-dev/bin/python >/dev/null 2>&1 && \
		../../.venv-dev/bin/python tui.py || python3 tui.py

dev:
	./dev.sh

install:
	@command -v ../../.venv-dev/bin/pip >/dev/null 2>&1 && \
		../../.venv-dev/bin/pip install -r requirements.txt || \
		pip install -r requirements.txt

catalog:
	python3 scripts/build_catalog.py

test:
	python3 -m unittest discover -s tests -v
