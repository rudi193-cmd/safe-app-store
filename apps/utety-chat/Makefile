# UTETY app-local targets (run from apps/utety-chat/)
CAMPUS_DIR := campus
CATALOG_SCRIPT := $(CAMPUS_DIR)/catalog/generate_catalog.py

.PHONY: campus tui catalog test

# Ratatui archival terminal
campus: catalog
	cargo run --manifest-path $(CAMPUS_DIR)/Cargo.toml

# Textual faculty chat (requires: pip install -r requirements-tui.txt)
tui:
	@command -v ../../.venv-dev/bin/python >/dev/null 2>&1 && \
		../../.venv-dev/bin/python tui.py || python3 tui.py

catalog:
	@python3 $(CATALOG_SCRIPT)

test:
	@command -v ../../.venv-dev/bin/python >/dev/null 2>&1 && \
		../../.venv-dev/bin/python -m unittest discover -s tests -v || \
		python3 -m unittest discover -s tests -v
