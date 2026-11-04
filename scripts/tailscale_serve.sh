#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${BIOFORGE_PORT:-8010}"
if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale is not installed. Install it on the server and phone, then sign in to the same tailnet." >&2
  exit 1
fi
if grep -q '^password: bioforge-demo' "$ROOT/runtime/login.txt" 2>/dev/null; then
  echo "WARNING: the server still uses the demo password. Change it before exposing the service." >&2
fi
echo "Publishing this tailnet-only service: http://127.0.0.1:${PORT}"
tailscale serve --bg "http://127.0.0.1:${PORT}"
echo
tailscale serve status
echo
echo "On the phone: install Tailscale, sign in to the same tailnet, then open the https://*.ts.net URL above."
echo "This is not a public tunnel. Use Cloudflare Tunnel + Access if external collaborators need access."
