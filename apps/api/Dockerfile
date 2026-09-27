# Adaptive Room Planner API (FastAPI + usd-core). Build from the repo root so the image can include the preset catalog and fixtures:
#   docker build -f apps/api/Dockerfile -t roomplanner-api .
#   docker run --rm -p 8080:8080 --env-file .env roomplanner-api
# The image runs with MOCK_MODE=false: GEMINI_API_KEY, BACKBOARD_API_KEY, MONGODB_URI and BLOB_READ_WRITE_TOKEN must be set or it exits.
# usd-core publishes Linux wheels for x86_64 only, so the image is always amd64 (App Platform runs amd64; Apple Silicon emulates).
FROM --platform=linux/amd64 python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MOCK_MODE=false \
    ARP_DATA_DIR=/tmp/arp-data \
    PORT=8080

WORKDIR /srv
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install -r apps/api/requirements.txt \
    && python -c "from pxr import Usd, UsdGeom; print('usd-core', Usd.GetVersion())"

# App code plus the repo files it reads at runtime (config.py resolves them relative to /srv).
COPY apps/api/app apps/api/app
COPY apps/api/scripts apps/api/scripts
COPY apps/api/seed_presets.py apps/api/
COPY packages/contracts/rules.json packages/contracts/rules.json
COPY assets assets
COPY fixtures/rooms fixtures/rooms
COPY fixtures/listings fixtures/listings
COPY fixtures/plans fixtures/plans

RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /srv/apps/api
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
