#!/usr/bin/env bash
set -euo pipefail
PORT="${MCP_PORT:-8000}"
exec ngrok http "$PORT"
