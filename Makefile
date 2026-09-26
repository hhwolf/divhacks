SHELL := /bin/bash
PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn

.PHONY: setup api web mobile test bench demo thumbs screenshots

setup: .venv/.ok node_modules/.ok

.venv/.ok:
	python3 -m venv .venv && .venv/bin/pip install -q -r apps/api/requirements.txt && touch .venv/.ok

node_modules/.ok:
	pnpm install && touch node_modules/.ok

api: setup
	cd apps/api && ../../$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

web: setup
	pnpm --filter @arp/web dev --host

mobile: setup
	cd apps/mobile && npx expo start --dev-client

test: setup
	pnpm typecheck && pnpm lint && pnpm test && cd apps/api && ../../$(PY) -m pytest -q

bench: setup
	pnpm --filter @arp/geometry bench
	cd apps/api && ../../$(PY) -m pytest -q tests/test_parity.py
	$(PY) scripts/bench_report.py

thumbs: setup
	$(PY) scripts/render_thumbs.py

screenshots: setup
	$(PY) scripts/screenshots.py

demo: setup
	$(PY) scripts/demo.py
