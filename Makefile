APP ?= story-timeline

.PHONY: run install list

run:
	cd apps/$(APP) && python3 app.py

install:
	cd apps/$(APP) && pip install -r requirements.txt

list:
	@python3 -c "import json; c=json.load(open('catalog.json')); [print(f\"  {a['id']:<25} {a['status']:<8} {a['description'][:60]}\") for a in c['apps']]"
