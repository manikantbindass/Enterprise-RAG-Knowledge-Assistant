# Enterprise RAG Knowledge Assistant — Makefile
# ================================================
.PHONY: help dev dev-down logs build test migrate seed clean lint format

# Colors
CYAN  := \033[36m
RESET := \033[0m

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────────────────────

dev: ## Start full development stack
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo "$(CYAN)Services started:$(RESET)"
	@echo "  Frontend:   http://localhost:3000"
	@echo "  API:        http://localhost:8000/docs"
	@echo "  Keycloak:   http://localhost:8080"
	@echo "  Grafana:    http://localhost:3001"
	@echo "  RabbitMQ:   http://localhost:15672"
	@echo "  MinIO:      http://localhost:9001"

dev-down: ## Stop development stack
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

dev-rebuild: ## Rebuild and restart services
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

logs: ## Tail all service logs
	docker compose logs -f --tail=100

logs-api: ## Tail API gateway logs
	docker compose logs -f api_gateway --tail=100

logs-chat: ## Tail chat service logs
	docker compose logs -f chat_service --tail=100

shell-api: ## Open shell in API gateway container
	docker compose exec api_gateway bash

shell-db: ## Open psql shell
	docker compose exec postgres psql -U rag_user -d rag_assistant

# ── Database ──────────────────────────────────────────────────────────────────

migrate: ## Run Alembic database migrations
	docker compose exec api_gateway alembic upgrade head

migrate-down: ## Rollback last migration
	docker compose exec api_gateway alembic downgrade -1

migrate-create: ## Create new migration (use: make migrate-create MSG="description")
	docker compose exec api_gateway alembic revision --autogenerate -m "$(MSG)"

seed: ## Seed development data
	docker compose exec api_gateway python scripts/seed.py

reset-db: ## Drop and recreate database (DESTRUCTIVE)
	docker compose exec postgres psql -U rag_user -c "DROP DATABASE IF EXISTS rag_assistant;"
	docker compose exec postgres psql -U rag_user -c "CREATE DATABASE rag_assistant;"
	$(MAKE) migrate
	$(MAKE) seed

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## Run all tests
	cd backend && python -m pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing

test-unit: ## Run unit tests only
	cd backend && python -m pytest tests/unit/ -v

test-integration: ## Run integration tests
	cd backend && python -m pytest tests/integration/ -v

test-load: ## Run load tests with Locust
	cd tests/load && locust -f locustfile.py --headless -u 100 -r 10 --run-time 60s

test-rag: ## Run RAG evaluation tests
	cd backend && python tests/rag_eval/evaluate.py

test-security: ## Run security scan (bandit + safety)
	cd backend && bandit -r . -x tests/
	cd backend && safety check

# ── Code Quality ──────────────────────────────────────────────────────────────

lint: ## Run linters (ruff + mypy + eslint)
	cd backend && ruff check . && mypy . --ignore-missing-imports
	cd frontend && npm run lint

format: ## Auto-format code (ruff + prettier)
	cd backend && ruff format .
	cd frontend && npx prettier --write .

# ── Build ─────────────────────────────────────────────────────────────────────

build: ## Build all Docker images
	docker compose build

build-frontend: ## Build frontend production bundle
	cd frontend && npm run build

push: ## Push Docker images to registry (set REGISTRY env var)
	docker compose push

# ── Infrastructure ────────────────────────────────────────────────────────────

k8s-apply: ## Apply Kubernetes manifests
	kubectl apply -f infrastructure/kubernetes/

k8s-delete: ## Delete Kubernetes resources
	kubectl delete -f infrastructure/kubernetes/

helm-install: ## Install Helm chart
	helm install rag-assistant infrastructure/helm/rag-assistant/ \
		--namespace rag-prod \
		--create-namespace \
		--values infrastructure/helm/values.prod.yaml

helm-upgrade: ## Upgrade Helm chart
	helm upgrade rag-assistant infrastructure/helm/rag-assistant/ \
		--namespace rag-prod \
		--values infrastructure/helm/values.prod.yaml

terraform-init: ## Initialize Terraform
	cd infrastructure/terraform/aws && terraform init

terraform-plan: ## Plan Terraform changes
	cd infrastructure/terraform/aws && terraform plan

terraform-apply: ## Apply Terraform changes
	cd infrastructure/terraform/aws && terraform apply

# ── Utilities ─────────────────────────────────────────────────────────────────

clean: ## Remove all containers, volumes, images
	docker compose down -v --remove-orphans
	docker image prune -f

setup-keycloak: ## Import Keycloak realm configuration
	docker compose exec keycloak /opt/keycloak/bin/kc.sh import --file /opt/keycloak/data/import/realm-export.json

generate-secret: ## Generate a random secret key
	python -c "import secrets; print(secrets.token_hex(32))"

check-health: ## Check health of all services
	curl -s http://localhost:8000/health | python -m json.tool
	curl -s http://localhost:8001/health | python -m json.tool
