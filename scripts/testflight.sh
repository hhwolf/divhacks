#!/usr/bin/env bash
# Build the iOS app with the live URLs baked in, archive, and upload to TestFlight — no Xcode GUI.
#
# Requires: Xcode 26+ (Expo SDK 57), and an App Store Connect API key:
#   ASC_KEY_ID=XXXXXXXXXX ASC_ISSUER_ID=<uuid> ASC_KEY_PATH=~/Downloads/AuthKey_XXXXXXXXXX.p8 APPLE_TEAM_ID=XXXXXXXXXX
# Optional: BUNDLE_ID (default dev.roomplanner.app), BUILD_NUMBER (default = unix minutes), SCHEME (default RoomPlanner)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT/apps/mobile"
: "${ASC_KEY_ID:?set ASC_KEY_ID}"; : "${ASC_ISSUER_ID:?set ASC_ISSUER_ID}"; : "${ASC_KEY_PATH:?set ASC_KEY_PATH}"; : "${APPLE_TEAM_ID:?set APPLE_TEAM_ID}"
BUNDLE_ID="${BUNDLE_ID:-dev.roomplanner.app}"; SCHEME="${SCHEME:-RoomPlanner}"; BUILD_NUMBER="${BUILD_NUMBER:-$(( $(date +%s) / 60 ))}"
API_URL="${PUBLIC_API_URL:-https://adaptive-room-planner-api.vercel.app}"; WEB_URL="${PUBLIC_WEB_URL:-https://adaptive-room-planner.vercel.app}"

XCODE_MAJOR="$(xcodebuild -version | head -1 | awk '{print $2}' | cut -d. -f1)"
if [ "$XCODE_MAJOR" -lt 26 ]; then echo "Xcode 26+ required for Expo SDK 57 (found $(xcodebuild -version | head -1))"; exit 2; fi

echo "→ baking URLs"; printf 'EXPO_PUBLIC_API_URL=%s\nEXPO_PUBLIC_WEB_URL=%s\n' "$API_URL" "$WEB_URL" > .env
echo "→ bundle id $BUNDLE_ID, build $BUILD_NUMBER"
node -e "const f='app.json';const j=require('./'+f);j.expo.ios.bundleIdentifier='$BUNDLE_ID';j.expo.ios.buildNumber='$BUILD_NUMBER';require('fs').writeFileSync(f,JSON.stringify(j,null,2)+'\n')"
echo "→ prebuild"; npx expo prebuild --platform ios --clean >/tmp/prebuild.log 2>&1 || { tail -30 /tmp/prebuild.log; exit 1; }

ARCHIVE="/tmp/RoomPlanner.xcarchive"; EXPORT="/tmp/RoomPlanner-export"; rm -rf "$ARCHIVE" "$EXPORT"
AUTH=(-allowProvisioningUpdates -allowProvisioningDeviceRegistration -authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
echo "→ archive"; xcodebuild -workspace "ios/$SCHEME.xcworkspace" -scheme "$SCHEME" -configuration Release -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CODE_SIGN_STYLE=Automatic PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" "${AUTH[@]}" archive 2>&1 | tail -5
cat > /tmp/exportOptions.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>signingStyle</key><string>automatic</string>
  <key>teamID</key><string>$APPLE_TEAM_ID</string>
  <key>uploadSymbols</key><true/>
  <key>manageAppVersionAndBuildNumber</key><true/>
</dict></plist>
PLIST
echo "→ export + upload"; xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist /tmp/exportOptions.plist -exportPath "$EXPORT" "${AUTH[@]}" 2>&1 | tail -8
echo "Uploaded build $BUILD_NUMBER of $BUNDLE_ID. It appears under TestFlight in App Store Connect after processing (usually < 15 min)."
