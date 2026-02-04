# Makefile for Planet CF development tasks
# Usage: make <target>

.PHONY: test test-cov lint vulture check fmt help

# Default target
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─────────────────────────────────────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────────────────────────────────────

test: ## Run tests normally (unit + integration)
	uv run pytest tests/unit tests/integration -x -q

test-cov: ## Run tests with coverage report (shows untested lines)
	uv run pytest tests/unit tests/integration -x -q --cov=src --cov-report=term-missing

test-unit: ## Run only unit tests
	uv run pytest tests/unit -x -q

test-integration: ## Run only integration tests
	uv run pytest tests/integration -x -q

# ─────────────────────────────────────────────────────────────────────────────
# Linting & Formatting
# ─────────────────────────────────────────────────────────────────────────────

lint: ## Run all linters (ruff check + ruff format --check + ty check)
	uvx ruff check .
	uvx ruff format --check .
	uvx ty check src/

fmt: ## Auto-format code with ruff
	uvx ruff check --fix .
	uvx ruff format .

vulture: ## Run dead code detection with vulture
	uvx vulture src/ vulture_whitelist.py

# ─────────────────────────────────────────────────────────────────────────────
# Combined Targets
# ─────────────────────────────────────────────────────────────────────────────

check: lint vulture test ## Run full CI check (lint + vulture + test)

check-all: lint vulture test-cov ## Run full CI check with coverage
