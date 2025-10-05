# AI Agent Platform API Gateway - Development Commands

.PHONY: help install dev test lint format clean docker-build docker-run docker-stop

# Default target
help: ## Show this help message
	@echo "AI Agent Platform API Gateway - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development Setup
install: ## Install dependencies
	pip install -r requirements.txt

venv: ## Create virtual environment
	python -m venv venv
	@echo "Activate with: source venv/bin/activate (Linux/Mac) or venv\\Scripts\\activate (Windows)"

dev: ## Start development server
	python run.py

dev-reload: ## Start development server with auto-reload
	uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Testing
test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/ -v -m "not integration"

test-integration: ## Run integration tests only
	pytest tests/ -v -m integration

test-cov: ## Run tests with coverage report
	pytest tests/ --cov=src --cov-report=html --cov-report=term

# Code Quality
lint: ## Run linting checks
	flake8 src/ tests/
	mypy src/

format: ## Format code
	black src/ tests/
	isort src/ tests/

format-check: ## Check code formatting
	black --check src/ tests/
	isort --check-only src/ tests/

# Docker Commands
docker-build: ## Build Docker image
	docker build -t ai-agent-gateway:latest .

docker-run: ## Run with Docker Compose
	docker-compose up -d

docker-stop: ## Stop Docker Compose services
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f gateway

docker-monitoring: ## Start with monitoring stack
	docker-compose --profile monitoring up -d

# Redis Commands
redis-start: ## Start Redis server (local)
	redis-server

redis-cli: ## Connect to Redis CLI
	redis-cli

redis-flush: ## Flush Redis cache
	redis-cli FLUSHALL

# Health Checks
health: ## Check API health
	curl -s http://localhost:8000/health | jq .

status: ## Check detailed API status
	curl -s http://localhost:8000/status | jq .

metrics: ## View Prometheus metrics
	curl -s http://localhost:8000/metrics

# Cleanup
clean: ## Clean up temporary files
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

clean-docker: ## Clean up Docker resources
	docker-compose down -v
	docker system prune -f

# Documentation
docs-serve: ## Serve API documentation
	@echo "API Documentation available at:"
	@echo "  Swagger UI: http://localhost:8000/docs"
	@echo "  ReDoc: http://localhost:8000/redoc"
	@echo "  OpenAPI JSON: http://localhost:8000/openapi.json"

# Production
prod-build: ## Build for production
	docker build -t ai-agent-gateway:prod --target production .

prod-run: ## Run production container
	docker run -d --name ai-agent-gateway-prod \
		-p 8000:8000 \
		--env-file .env \
		ai-agent-gateway:prod
