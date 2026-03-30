#!/bin/sh
set -e
cd "$(dirname "$0")"

echo "Starting Postgres..."
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pre_ipo --name preipo-postgres postgres:15 2>/dev/null || docker start preipo-postgres 2>/dev/null

echo "Waiting for Postgres..."
until docker exec preipo-postgres pg_isready -U postgres -d pre_ipo 2>/dev/null; do sleep 2; done

echo "Running migrations..."
for migration in backend/database/migrations/*.sql; do
  docker exec -i preipo-postgres psql -U postgres -d pre_ipo -v ON_ERROR_STOP=1 < "$migration"
done

echo "Done. Run in separate terminals:"
echo "  Terminal 1: PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000"
echo "  Terminal 2: cd frontend && npm run dev"
