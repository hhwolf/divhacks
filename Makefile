SHELL := /bin/bash
PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn

.PHONY: setup api web mobile test bench demo e2e thumbs screenshots fps record docker-api seed verify

setup: .venv/.ok node_modules/.ok

.venv/.ok:
	python3.12 -m venv .venv && .venv/bin/pip install -q -r apps/api/requirements-dev.txt && touch .venv/.ok

node_modules/.ok:
	npx -y pnpm@10 install && touch node_modules/.ok

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

e2e: setup
	$(PY) scripts/e2e_editor.py

fps: setup
	$(PY) scripts/measure_fps.py

record: setup
	$(PY) scripts/record_demo.py

verify: setup
	cd apps/api && ../../$(PY) scripts/verify_requirements.py

docker-api:
	docker build -f apps/api/Dockerfile -t roomplanner-api . && docker run --rm -p 8080:8080 --env-file .env roomplanner-api

seed: setup
	cd apps/api && ../../$(PY) seed_presets.py
