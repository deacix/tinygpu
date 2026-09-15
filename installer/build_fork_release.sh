#!/bin/bash
# Build the x1476 TinyGPU fork as an ad-hoc-signed app for SIP-off machines
# (System Settings > Privacy & Security > Reduced Security + `csrutil disable`,
# then `systemextensionsctl developer on`). Produces dist/TinyGPU.zip and its
# SHA-256, the shape x1476's engines manifest pins (tinygpu.app.url + sha256).
#
# Signing: ad hoc, with the vendor-scoped Release entitlements (NVIDIA 0x10de
# and AMD 0x1002), not the match-anything NoSIP set upstream's dev script uses.
# AMFI only accepts these restricted entitlements on an ad-hoc signature when
# SIP is off; on a SIP-on Mac use tinygrad's signed release instead.
set -euo pipefail

cd "$(dirname "$0")"

CONFIGURATION="${CONFIGURATION:-Release}"
APP_PATH="./build/$CONFIGURATION/TinyGPU.app"
DEXT_PATH="$APP_PATH/Contents/Library/SystemExtensions/org.tinygrad.tinygpu.driver2.dext"
DIST="./dist"

xcodebuild clean build CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO -alltargets -configuration "$CONFIGURATION" build \
  | grep -E "error:|BUILD (SUCCEEDED|FAILED)" || true
[ -d "$APP_PATH" ] || { echo "build did not produce $APP_PATH" >&2; exit 1; }

# The provisioning profiles belong to tinygrad's team; an ad-hoc build must not carry them.
rm -f "$APP_PATH/Contents/embedded.provisionprofile" "$DEXT_PATH/embedded.provisionprofile"

codesign --sign - --entitlements ./TinyGPUDriverExtension/TinyGPUDriver.Release.entitlements --force --timestamp=none --verbose "$DEXT_PATH"
codesign --sign - --entitlements ./macOS/macOS.entitlements --force --timestamp=none --verbose "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

mkdir -p "$DIST"
rm -f "$DIST/TinyGPU.zip"
# ditto -c -k keeps the bundle layout x1476 extracts with `ditto -xk` (same as upstream's TinyGPU.zip).
ditto -c -k --keepParent "$APP_PATH" "$DIST/TinyGPU.zip"
shasum -a 256 "$DIST/TinyGPU.zip" | tee "$DIST/TinyGPU.zip.sha256"

# A .dext bundle is flat: Info.plist sits at its root, not under Contents/.
DEXT_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$DEXT_PATH/Info.plist")"
DEXT_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$DEXT_PATH/Info.plist")"
echo "built $APP_PATH (dext $DEXT_VERSION/$DEXT_BUILD) -> $DIST/TinyGPU.zip"
