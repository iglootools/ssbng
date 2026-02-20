.PHONY: install test test-integration test-all format lint type-check clean build publish help

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	poetry install

test: ## Run unit tests (no Docker)
	poetry run pytest tests/ --ignore=tests/integration/ -v

test-integration: ## Run integration tests (requires Docker)
	poetry run pytest tests/integration/ -v

test-all: ## Run all tests
	poetry run pytest tests/ -v

format: ## Format code with black
	poetry run black .

lint: ## Run flake8 linting
	poetry run flake8 dab/ tests/

type-check: ## Run mypy type checking
	poetry run mypy dab/

check: format lint type-check test ## Run all checks (format, lint, type-check, test)

clean: ## Clean up build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

build: ## Build the package
	poetry build

publish: ## Publish to PyPI (requires authentication)
	poetry publish

example: ## Run the basic usage example
	poetry run python examples/basic_usage.py

shell: ## Start a Poetry shell
	poetry shell
