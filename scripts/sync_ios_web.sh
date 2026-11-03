#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$ROOT/web"
TARGET="$ROOT/ios/www"

if [ ! -f "$SOURCE/index.html" ]; then
  echo "missing $SOURCE/index.html" >&2
  exit 1
fi

rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -R "$SOURCE"/. "$TARGET"/

if [ ! -f "$TARGET/index.html" ] || [ ! -f "$TARGET/app.js" ] || [ ! -f "$TARGET/styles.css" ]; then
  echo "iOS web asset sync failed" >&2
  exit 1
fi

echo "synced $(find "$TARGET" -type f | wc -l | tr -d ' ') files to $TARGET"
grep -m1 'const CACHE' "$TARGET/sw.js" || true
