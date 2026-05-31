#!/usr/bin/env bash
set -euo pipefail
docker-compose up -d
echo "Waiting for postgres to be healthy..."
until docker-compose exec postgres pg_isready -U flowuser -d flow_intel; do sleep 1; done
echo "Running alembic upgrade..."
uv run alembic upgrade head
echo "DB ready."
