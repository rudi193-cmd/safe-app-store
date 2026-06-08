APP    ?= story-timeline
VENV   := $(CURDIR)/.venv-dev
PYTHON := $(VENV)/bin/python3
PIP    := $(VENV)/bin/pip

.PHONY: run install venv list

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip -q

run: venv
	cd apps/$(APP) && $(PYTHON) app.py

install: venv
	$(PIP) install -r apps/$(APP)/requirements.txt

list:
	@python3 -c "import json; c=json.load(open('catalog.json')); [print(f\"  {a['id']:<25} {a['status']:<8} {a['description'][:60]}\") for a in c['apps']]"
