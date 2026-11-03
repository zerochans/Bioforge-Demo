#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/runtime/secrets/postgres.env"
PYTHON="${PYTHON:-/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python}"
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  PW="$(openssl rand -hex 24)"
  printf 'POSTGRES_USER=bioforge\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=bioforge\nDATABASE_URL=postgresql://bioforge:%s@127.0.0.1:5432/bioforge\n' "$PW" "$PW" > "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
set -a
. "$ENV_FILE"
set +a
if ! docker image inspect pgvector/pgvector:pg16 >/dev/null 2>&1; then
  docker pull pgvector/pgvector:pg16
fi
if docker container inspect bioforge-db >/dev/null 2>&1; then
  docker start bioforge-db >/dev/null
else
  docker run -d --name bioforge-db --restart unless-stopped \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="$POSTGRES_DB" \
    -p 127.0.0.1:5432:5432 \
    -v bioforge_pgdata:/var/lib/postgresql/data \
    pgvector/pgvector:pg16 >/dev/null
fi
for _ in $(seq 1 45); do
  docker exec bioforge-db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1 && break
  sleep 1
done
docker exec bioforge-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
"$PYTHON" "$ROOT/scripts/sync_postgres.py"
