#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH=backend
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
