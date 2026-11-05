#!/usr/bin/env bash
set -euo pipefail
bash /workspace/scripts/init-ns3.sh
exec python3 -m uvicorn api.complete_api:app --app-dir /workspace/examples/Reverie --host 0.0.0.0 --port 8000
