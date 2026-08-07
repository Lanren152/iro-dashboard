#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m app.seed
printf '\nBootstrap complete. Run: make dev-backend, make dev-frontend, make dev-mcp\n'
