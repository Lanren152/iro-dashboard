SHELL := /bin/bash

bootstrap:
	python -m venv .venv
	. .venv/bin/activate && pip install -r backend/requirements.txt

seed:
	. .venv/bin/activate && PYTHONPATH=backend python -m app.seed

dev-backend:
	. .venv/bin/activate && PYTHONPATH=backend uvicorn app.main:app --reload --port 8000

dev-mcp:
	. .venv/bin/activate && PYTHONPATH=backend python -m app.mcp_server

dev-frontend:
	cd frontend && python -m http.server 3000

test:
	. .venv/bin/activate && PYTHONPATH=backend pytest -q backend/tests

lint:
	. .venv/bin/activate && ruff check backend
	python -m compileall -q backend/app

build:
	@echo "Static frontend requires no build step"

demo-cycle:
	curl -s -X POST http://localhost:8000/api/research/run-cycle | python -m json.tool
