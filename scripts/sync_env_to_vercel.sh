#!/usr/bin/env bash
# Push the real-mode keys from .env to the deployed API (Vercel project adaptive-room-planner-api) and redeploy.
# Usage: scripts/sync_env_to_vercel.sh   (reads .env in the repo root; only the variables listed below are synced)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[ -f .env ] || { echo ".env not found — copy .env.example and add keys first"; exit 1; }
SCOPE="${VERCEL_SCOPE:-ast18}"
for VAR in MOCK_MODE GEMINI_API_KEY GEMINI_MODEL BACKBOARD_API_KEY BACKBOARD_BASE_URL PHOTON_API_KEY PHOTON_WEBHOOK_SECRET PHOTON_BASE_URL PHOTON_FROM MONGODB_URI MONGODB_DB DEMO_PHONE; do
  VAL="$(grep -E "^${VAR}=" .env | head -1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//' | tr -d '"' || true)"
  [ -n "$VAL" ] || continue
  vercel env rm "$VAR" production --yes --scope "$SCOPE" >/dev/null 2>&1 || true
  printf '%s' "$VAL" | vercel env add "$VAR" production --scope "$SCOPE" >/dev/null && echo "synced $VAR"
done
vercel env add PUBLIC_WEB_URL production --scope "$SCOPE" <<< "https://adaptive-room-planner.vercel.app" >/dev/null 2>&1 || true
vercel env add PUBLIC_API_URL production --scope "$SCOPE" <<< "https://adaptive-room-planner-api.vercel.app" >/dev/null 2>&1 || true
vercel deploy --prod --yes --scope "$SCOPE" | tail -1
curl -s https://adaptive-room-planner-api.vercel.app/health; echo
