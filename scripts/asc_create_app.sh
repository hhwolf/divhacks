#!/usr/bin/env bash
# Create the App Store Connect app record for the bundle id (needed once before the first upload).
# Env: ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_PATH BUNDLE_ID(default dev.roomplanner.app) APP_NAME(default "FitCheck")
set -euo pipefail
: "${ASC_KEY_ID:?}"; : "${ASC_ISSUER_ID:?}"; : "${ASC_KEY_PATH:?}"
BUNDLE_ID="${BUNDLE_ID:-dev.roomplanner.app}"; APP_NAME="${APP_NAME:-FitCheck}"; SKU="${SKU:-adaptive-room-planner-$(date +%s)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN="$("$ROOT/.venv/bin/python" - <<PY
import time, jwt  # PyJWT
key=open("$ASC_KEY_PATH").read()
print(jwt.encode({"iss":"$ASC_ISSUER_ID","iat":int(time.time()),"exp":int(time.time())+1200,"aud":"appstoreconnect-v1"}, key, algorithm="ES256", headers={"kid":"$ASC_KEY_ID"}))
PY
)"
api() { curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"; }
BID_ID="$(api "https://api.appstoreconnect.apple.com/v1/bundleIds?filter[identifier]=$BUNDLE_ID" | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]; print(d[0]["id"] if d else "")')"
if [ -z "$BID_ID" ]; then
  echo "→ registering bundle id $BUNDLE_ID"
  BID_ID="$(api -X POST https://api.appstoreconnect.apple.com/v1/bundleIds -d "{\"data\":{\"type\":\"bundleIds\",\"attributes\":{\"identifier\":\"$BUNDLE_ID\",\"name\":\"FitCheck\",\"platform\":\"IOS\"}}}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["id"])')"
fi
EXISTING="$(api "https://api.appstoreconnect.apple.com/v1/apps?filter[bundleId]=$BUNDLE_ID" | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]; print(d[0]["id"] if d else "")')"
if [ -n "$EXISTING" ]; then echo "app record exists ($EXISTING)"; exit 0; fi
echo "→ creating app record"
api -X POST https://api.appstoreconnect.apple.com/v1/apps -d "{\"data\":{\"type\":\"apps\",\"attributes\":{\"name\":\"$APP_NAME\",\"bundleId\":\"$BUNDLE_ID\",\"sku\":\"$SKU\",\"primaryLocale\":\"en-US\"}}}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("data",{}).get("id") or d)'
