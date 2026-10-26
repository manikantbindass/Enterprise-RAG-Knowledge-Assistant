.PHONY: dev build test lint docker

dev:
	python -m uvicorn backend.runtime.main:app --host 127.0.0.1 --port 8000

build:
	cd frontend && npm run build

test:
	python -m pytest backend/runtime/tests -q --confcutdir=backend/runtime/tests
	cd frontend && npm test

lint:
	python -m ruff check backend/runtime
	cd frontend && npm run lint
	cd frontend && npm run typecheck

docker:
	docker compose up --build
