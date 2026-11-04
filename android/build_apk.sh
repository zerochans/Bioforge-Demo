#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK="${ANDROID_SDK_ROOT:-$ROOT/android/sdk}"
BT="$SDK/build-tools/34.0.0"
ANDROID_JAR="$SDK/platforms/android-34/android.jar"
APP="$ROOT/android/app"
BUILD="$ROOT/android/build"
DIST="$ROOT/dist"
KS="$ROOT/android/keystore/bioforge.keystore"
KS_PASS="bioforge-local"
PYTHON="${PYTHON:-python3}"

"$PYTHON" "$ROOT/scripts/build_web_data.py"

rm -rf "$BUILD"
mkdir -p "$BUILD/gen" "$BUILD/classes" "$BUILD/dex" "$DIST"

"$BT/aapt2" compile --dir "$APP/src/main/res" -o "$BUILD/res.zip"
"$BT/aapt2" link \
  -o "$BUILD/app-unsigned.apk" \
  -I "$ANDROID_JAR" \
  --manifest "$APP/AndroidManifest.xml" \
  -R "$BUILD/res.zip" \
  -A "$APP/src/main/assets" \
  --java "$BUILD/gen" \
  --min-sdk-version 24 \
  --target-sdk-version 34 \
  --version-code 9 \
  --version-name 3.3.0 \
  --auto-add-overlay

find "$APP/src/main/java" "$BUILD/gen" -name '*.java' > "$BUILD/sources.txt"
javac -source 8 -target 8 -classpath "$ANDROID_JAR" -d "$BUILD/classes" @"$BUILD/sources.txt"
find "$BUILD/classes" -name '*.class' > "$BUILD/classes.txt"
"$BT/d8" --lib "$ANDROID_JAR" --min-api 24 --output "$BUILD/dex" $(cat "$BUILD/classes.txt")
(cd "$BUILD" && zip -q -j app-unsigned.apk dex/classes.dex)
"$BT/zipalign" -f 4 "$BUILD/app-unsigned.apk" "$BUILD/app-aligned.apk"

if [ ! -f "$KS" ]; then
  mkdir -p "$(dirname "$KS")"
  keytool -genkeypair -v \
    -keystore "$KS" \
    -alias bioforge \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass "$KS_PASS" \
    -keypass "$KS_PASS" \
    -dname "CN=BioForge Studio, O=Local Research, C=CN" >/dev/null 2>&1
  chmod 600 "$KS"
fi

APK="$DIST/BioForgeStudio-3.3.0.apk"
"$BT/apksigner" sign \
  --ks "$KS" \
  --ks-pass "pass:$KS_PASS" \
  --key-pass "pass:$KS_PASS" \
  --out "$APK" \
  "$BUILD/app-aligned.apk"
"$BT/apksigner" verify --verbose --print-certs "$APK"
ls -lh "$APK"
