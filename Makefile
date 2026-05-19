.PHONY: help install lint format test bump

rule ?= patch

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	poetry install --with dev

lint: ## Run linters
	poetry run ruff check src/
	poetry run black --check src/

format: ## Format code
	poetry run black src/
	poetry run ruff check --fix src/

test: ## Run tests
	poetry run pytest

bump: ## Bump version (rule=patch|minor|major)
	poetry version $(rule)
	git add pyproject.toml
	git commit -m "bump: v$$(poetry version -s)"
	git tag v$$(poetry version -s)
