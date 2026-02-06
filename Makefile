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
# Setup & Dependencies
# ─────────────────────────────────────────────────────────────────────────────

python-modules: ## Create python_modules from pyodide venv (required for deployment)
	@if [ ! -d ".venv-workers/pyodide-venv/lib" ]; then \
		echo "Error: .venv-workers/pyodide-venv not found."; \
		echo "Run 'uv sync' first to create the pyodide virtual environment."; \
		exit 1; \
	fi
	@if [ -d "python_modules" ]; then \
		echo "python_modules already exists - removing and recreating..."; \
		rm -rf python_modules; \
	fi
	@SITE_PACKAGES=$$(find .venv-workers/pyodide-venv/lib -name "site-packages" -type d | head -1); \
	if [ -z "$$SITE_PACKAGES" ]; then \
		echo "Error: Could not find site-packages in pyodide venv"; \
		exit 1; \
	fi; \
	echo "Copying from $$SITE_PACKAGES..."; \
	cp -r "$$SITE_PACKAGES" python_modules; \
	echo "Created python_modules/ with bundled dependencies"

# ─────────────────────────────────────────────────────────────────────────────
# Validation & Deployment
# ─────────────────────────────────────────────────────────────────────────────

validate: ## Validate codebase is ready for deployment
	uv run python scripts/validate_deployment_ready.py

templates: ## Rebuild templates.py from template files
	uv run python scripts/build_templates.py

verify: ## Verify deployed sites are working (pass URLs as SITES="url1 url2")
	@if [ -z "$(SITES)" ]; then \
		echo "Usage: make verify SITES='https://site1.workers.dev https://site2.workers.dev'"; \
		exit 1; \
	fi
	uv run python scripts/verify_deployment.py $(SITES)

# ─────────────────────────────────────────────────────────────────────────────
# Combined Targets
# ─────────────────────────────────────────────────────────────────────────────

check: lint vulture test ## Run full CI check (lint + vulture + test)

check-all: lint vulture test-cov ## Run full CI check with coverage

pre-deploy: check validate ## Full pre-deployment check (lint + test + validate)
