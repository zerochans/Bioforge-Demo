#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_NAME="BioForgeStudio"
APP_VERSION="3.2.2"
BUILD_DIR="${IOS_BUILD_DIR:-$ROOT/ios/build}"
DERIVED="${IOS_DERIVED_DATA:-$BUILD_DIR/DerivedData}"
APP="$DERIVED/Build/Products/Release-iphoneos/$APP_NAME.app"
OUT="$ROOT/dist/$APP_NAME-$APP_VERSION-unsigned.ipa"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "iOS builds require macOS with Xcode; current host is $(uname -s)." >&2
  exit 1
fi
command -v xcodebuild >/dev/null || {
  echo "xcodebuild not found; install Xcode 15 or newer." >&2
  exit 1
}

"$ROOT/scripts/sync_ios_web.sh"
mkdir -p "$ROOT/dist" "$BUILD_DIR"
rm -rf "$DERIVED" "$OUT" "$OUT.sha256"

xcodebuild \
  -project "$ROOT/ios/$APP_NAME.xcodeproj" \
  -scheme "$APP_NAME" \
  -configuration Release \
  -destination "generic/platform=iOS" \
  -derivedDataPath "$DERIVED" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build

test -d "$APP" || {
  echo "missing built app: $APP" >&2
  exit 1
}
test -f "$APP/$APP_NAME" || {
  echo "missing app executable: $APP/$APP_NAME" >&2
  exit 1
}
test -f "$APP/www/index.html" || {
  echo "missing bundled www/index.html" >&2
  exit 1
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bioforge-ipa.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/Payload"
cp -R "$APP" "$WORK/Payload/"
(cd "$WORK" && /usr/bin/zip -qry "$OUT" Payload)

file "$APP/$APP_NAME"
unzip -l "$OUT" | sed -n '1,24p'
shasum -a 256 "$OUT" | sed "s|$ROOT/dist/||" > "$OUT.sha256"
cat "$OUT.sha256"
echo "unsigned IPA: $OUT"
