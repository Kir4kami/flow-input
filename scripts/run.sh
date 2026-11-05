#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose build fastapi
docker compose up -d --force-recreate fastapi
echo "UI: http://localhost:8000/complete_frontend.html"
echo "Build/startup logs: docker compose logs -f fastapi"
