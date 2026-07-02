# civics-check app-local targets (run from apps/civics-check/)

.PHONY: run tui

# Zero-dependency CLI (always works, no pip install needed)
run:
	python3 app.py

# Textual dashboard (requires: pip install -r requirements-tui.txt)
tui:
	@command -v ../../.venv-dev/bin/python >/dev/null 2>&1 && \
		../../.venv-dev/bin/python tui.py || python3 tui.py
