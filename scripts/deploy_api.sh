#!/usr/bin/env bash
# Deploy the FastAPI backend to Vercel (Python serverless, ASGI). Run from anywhere; requires `vercel login` once.
# Persistence: without MONGODB_URI the JSON store lives in /tmp and is per-instance/ephemeral — set MONGODB_URI in the
# Vercel project env for real persistence. Secrets go in the Vercel dashboard or `vercel env add <NAME> production`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
vercel deploy --prod --yes --scope "${VERCEL_SCOPE:-ast18}" 2>&1 | grep -E "Aliased|error" | tail -1
