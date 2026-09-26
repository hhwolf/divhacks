#!/usr/bin/env bash
# Deploy the web editor to Vercel as a static site. Requires `vercel login` once.
# Usage: scripts/deploy_web.sh https://<api-host>   (the public API URL baked into the bundle)
set -euo pipefail
API_URL="${1:-${PUBLIC_API_URL:-http://localhost:8000}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VITE_API_URL="$API_URL" pnpm --filter @arp/web build >/dev/null
cd apps/web/dist
# the build recreates dist/, so re-link it to the web project every time (otherwise Vercel creates a project named "dist")
vercel link --yes --project adaptive-room-planner --scope "${VERCEL_SCOPE:-ast18}" >/dev/null
vercel deploy --prod --yes --scope "${VERCEL_SCOPE:-ast18}" 2>&1 | grep -E "Aliased|error" | tail -1
