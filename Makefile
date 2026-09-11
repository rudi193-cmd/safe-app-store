APP    ?= story-timeline
# Docs use ``make run app=<name>`` — honor lowercase alias.
ifdef app
APP := $(app)
endif
VENV   := $(CURDIR)/.venv-dev
PYTHON := $(VENV)/bin/python3
PIP    := $(VENV)/bin/pip

.PHONY: run install venv list demo reconcile reconcile-apply

# Zero-config demo on synthetic data. Defaults to law-gazelle (the only app
# with a demo.sh so far); other apps opt in by adding their own demo.sh.
DEMO_APP := $(if $(app),$(app),law-gazelle)

demo:
	@test -x apps/$(DEMO_APP)/demo.sh || { echo "apps/$(DEMO_APP) has no demo.sh"; exit 1; }
	cd apps/$(DEMO_APP) && ./demo.sh

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip -q

run: venv
	cd apps/$(APP) && $(PYTHON) app.py

install: venv
	$(PIP) install -r apps/$(APP)/requirements.txt

list:
	@python3 -c "import json; c=json.load(open('.willow/store/catalog.json')); [print(f\"  {a['id']:<25} {a['status']:<8} {a['description'][:60]}\") for a in c['apps']]"

# The declared-vs-materialized store reconciler (docs/design/store-reconciler.md).
# `reconcile` is the drift report — the same muscle memory as `make list`; it
# exits non-zero if any missing/source_changed/stale remains, so CI can lean on
# it as an early drift signal ahead of the catalog_lint hard gate.
# `reconcile-apply` performs the additive, idempotent heal (never deletes
# without --allow-delete).
reconcile:
	@python3 tools/store_reconcile.py

reconcile-apply:
	@python3 tools/store_reconcile.py --apply
