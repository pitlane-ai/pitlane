.DEFAULT_GOAL := install

.PHONY: install test test-all coverage e2e lint format typecheck check pre-commit build clean

# ── Setup ─────────────────────────────────────────────────────────────────────

install:
	uv sync
	uv tool install .
	uv run pre-commit install

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	uv run pytest -m "not integration and not e2e"

test-all:
	uv run pytest -m "not e2e"

coverage:
	uv run pytest -m "not e2e" --cov=src/pitlane --cov-report=term-missing --cov-report=html

e2e:
	uv run pytest -m e2e -v --tb=long

e2e-%:
	uv run pytest -m e2e -v --tb=long -k $*

# ── Code Quality ──────────────────────────────────────────────────────────────

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

typecheck:
	uv run mypy src/pitlane

check: lint typecheck

pre-commit:
	uv run pre-commit run --all-files

# ── Build ─────────────────────────────────────────────────────────────────────

build:
	uv build

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf dist/ .coverage htmlcov/ .mypy_cache/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
