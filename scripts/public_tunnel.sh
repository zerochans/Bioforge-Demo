#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker or use Tailscale/VPS deployment." >&2
  exit 1
fi
if grep -q '^password: bioforge-demo' "$ROOT/runtime/login.txt" 2>/dev/null; then
  if [ "${BIOFORGE_TUNNEL_CONFIRM:-0}" != "1" ]; then
    echo "Refusing to expose the default demo password." >&2
    echo "Change the password in Settings, then rerun with BIOFORGE_TUNNEL_CONFIRM=1." >&2
    exit 1
  fi
  echo "WARNING: exposing a server that still uses the demo password." >&2
fi
ARGS=(--rm --add-host=host.docker.internal:host-gateway cloudflare/cloudflared:latest tunnel --no-autoupdate)
if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  echo "Starting named Cloudflare Tunnel (token from environment)…"
  exec docker run "${ARGS[@]}" run --token "$CLOUDFLARE_TUNNEL_TOKEN"
fi
echo "Starting a temporary Cloudflare Quick Tunnel. The URL is public and changes on restart." >&2
echo "For customers use a named tunnel with a stable hostname, or VPS + Caddy." >&2
exec docker run "${ARGS[@]}" --url http://host.docker.internal:8010
