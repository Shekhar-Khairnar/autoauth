#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec uvicorn mock_payer.main:app --port 8081 --reload
