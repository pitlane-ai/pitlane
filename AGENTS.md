# pitlane

Lightweight Python-based evaluation harness for AI coding assistants.

## Quick Reference

- **Package Manager:** uv
- **Install:** `make` (or `uv sync && uv tool install .`)
- **Run Eval:** `pitlane run examples/simple-codegen-eval.yaml`
- **Test:** `uv run pytest`
- **Pre-commit:** `uv run pre-commit run --all-files`

## Testing

- **Unit tests (fast, default):** `uv run pytest -m "not integration and not e2e"`
- **Unit + integration:** `uv run pytest -m "not e2e"`
- **E2E only (on-demand, requires all CLIs):** `uv run pytest -m e2e -v --tb=long`
- **E2E single assistant:** `uv run pytest -m e2e -v -k claude_code`
- **All tests:** `uv run pytest`

## Detailed Guidelines

For specific guidance, see:

- [Development Conventions](.agents/development.md) - TDD workflow, code quality, testing
- [YAML Configuration](.agents/yaml-config.md) - Benchmark structure, assertions
- [Assistant Implementation](.agents/assistants.md) - Creating new assistants
- [Architecture & Design](.agents/architecture.md) - Key decisions, project structure
