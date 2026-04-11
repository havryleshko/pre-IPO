#!/bin/sh
set -e
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running or not reachable. Start Docker Desktop, wait until it is ready, then run this script again." >&2
  exit 1
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  echo "Creating .env from .env.example (edit SEC_EDGAR_USER_AGENT and optional API keys)..."
  cp .env.example .env
fi

container_exists() {
  docker ps -a --format '{{.Names}}' | grep -qx preipo-postgres
}

host_port_published() {
  docker port preipo-postgres 5432/tcp 2>/dev/null | grep -q .
}

echo "Starting Postgres..."
if container_exists && ! host_port_published; then
  echo "Recreating preipo-postgres (5432 not published to host)..."
  docker rm -f preipo-postgres
fi
if ! container_exists; then
  echo "Creating container preipo-postgres (postgres:15). First image pull can take several minutes with no extra output from Docker."
  docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pre_ipo --name preipo-postgres postgres:15
  echo "Container created."
else
  echo "Starting existing container preipo-postgres..."
  docker start preipo-postgres
fi

echo "Waiting for Postgres to accept connections..."
until docker exec preipo-postgres pg_isready -U postgres -d pre_ipo 2>/dev/null; do sleep 2; done

echo "Running migrations..."
for migration in backend/database/migrations/*.sql; do
  [ -f "$migration" ] || continue
  echo "  $migration"
  cat "$migration" | docker exec -i preipo-postgres psql -U postgres -d pre_ipo -v ON_ERROR_STOP=1
done

if command -v pg_isready >/dev/null 2>&1; then
  echo "Verifying host can reach Postgres on 127.0.0.1:5432..."
  if pg_isready -h 127.0.0.1 -p 5432 -U postgres -d pre_ipo >/dev/null 2>&1; then
    echo "Host pg_isready: accepting connections"
  else
    echo "Warning: Postgres is running in Docker but 127.0.0.1:5432 is not accepting connections." >&2
    echo "Check Docker Desktop port forwarding or recreate the container with -p 5432:5432." >&2
  fi
fi

echo "Done. Run in separate terminals:"
echo "  Terminal 1: source .venv/bin/activate && PYTHONPATH=. uvicorn backend.main:app --host 127.0.0.1 --port 8000"
echo "  Terminal 2: source .venv/bin/activate && PREIPO_API_URL=http://127.0.0.1:8000 PREIPO_WS_URL=ws://127.0.0.1:8000 python -m tui"
