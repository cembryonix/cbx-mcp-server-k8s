# CBX MCP K8s Server - Development Makefile

.PHONY: help install lint lint-fix test test-functional test-integration clean run run-http docker-build docker-publish

PYTHON := python
PYTHONPATH := PYTHONPATH=app
PYTEST := $(PYTHONPATH) pytest

help:
	@echo "CBX MCP K8s Server - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies"
	@echo ""
	@echo "Quality:"
	@echo "  make lint             Run ruff linter"
	@echo "  make lint-fix         Run ruff with auto-fix"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-functional  Run functional tests only"
	@echo "  make test-integration Run integration tests only"
	@echo ""
	@echo "Run:"
	@echo "  make run              Run server (stdio transport)"
	@echo "  make run-http         Run server (HTTP transport)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build Docker image (local)"
	@echo "  make docker-publish   Build and push to registry"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove cache and build artifacts"

install:
	$(PYTHON) -m pip install --upgrade pip
	pip install -r requirements.txt
	pip install ruff mypy

lint:
	ruff check app/ tests/

lint-fix:
	ruff check app/ tests/ --fix

test:
	$(PYTEST) tests/ -v --tb=short

test-functional:
	$(PYTEST) tests/functional/ -v --tb=short

test-integration:
	$(PYTEST) tests/integration/ -v --tb=short

run:
	$(PYTHONPATH) $(PYTHON) app/main.py --transport stdio --skip-tool-validation

run-http:
	$(PYTHONPATH) $(PYTHON) app/main.py --transport streamable-http --port 8080 --skip-tool-validation

docker-build:
	./pkg/docker/build.sh

docker-publish:
	./pkg/docker/build.sh publish

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
