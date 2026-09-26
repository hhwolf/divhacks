#!/usr/bin/env bash
# Deploy the FastAPI backend to Vercel (Python serverless, ASGI). Run from anywhere; requires `vercel login` once.
# Persistence: without Supabase or Blob storage the JSON store lives in /tmp and is per-instance/ephemeral.
# Set SUPABASE_URL + SUPABASE_SECRET_KEY in the Vercel project env for real persistence.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
vercel deploy --prod --yes --scope "${VERCEL_SCOPE:-ast18}" 2>&1 | grep -E "Aliased|error" | tail -1
