#!/usr/bin/env bash
# Deploy the web editor to Vercel as a static site. Requires `vercel login` once.
# Usage: scripts/deploy_web.sh https://<api-host>   (the public API URL baked into the bundle)
set -euo pipefail
API_URL="${1:-${PUBLIC_API_URL:-http://localhost:8000}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VITE_API_URL="$API_URL" pnpm --filter @arp/web build >/dev/null
cd apps/web/dist
vercel deploy --prod --yes --name adaptive-room-planner 2>&1 | tail -1
