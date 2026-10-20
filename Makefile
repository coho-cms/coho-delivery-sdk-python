.PHONY: sync test lint format type check build bundle clean

sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

type:
	uv run mypy

# Everything CI runs.
check: lint type test

# Both wheels and sdists, into dist/.
build:
	uv build --package coho-delivery-sdk --out-dir dist
	uv build --package coho-codegen --out-dir dist

# Bundle a template checkout into coho-codegen, as the publish workflow does:
# make bundle TEMPLATE=../coho-template-python
TEMPLATE ?= ../coho-template-python
bundle:
	uv run python packages/codegen/scripts/bundle.py $(TEMPLATE)

clean:
	rm -rf dist build .pytest_cache .ruff_cache .mypy_cache
