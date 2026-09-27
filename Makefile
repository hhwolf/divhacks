SHELL := /bin/bash
PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn

.PHONY: setup api web mobile mobile-web test bench demo e2e thumbs screenshots photon fps record supabase-assets designer-check

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

# Mobile app in a browser (Expo web on :8081); view it in a phone frame at http://localhost:5173/device
mobile-web:
	cd apps/mobile && npx expo start --web --port 8081

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

# Interior-designer merge check: skill copy, 3D scene round-trip, rule agreement, GLB models, designer behavior (+ live Gemini quiz with a key)
designer-check: setup
	$(PY) apps/api/scripts/check_designer.py

photon: setup
	$(PY) scripts/simulate_photon.py

fps: setup
	$(PY) scripts/measure_fps.py

record: setup
	$(PY) scripts/record_demo.py

supabase-assets: setup
	$(PY) scripts/upload_furniture_assets.py
