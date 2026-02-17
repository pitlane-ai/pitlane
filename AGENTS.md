# pitlane

Lightweight Python-based evaluation harness for AI coding assistants.

## Quick Reference

- **Package Manager:** uv
- **Install:** `uv sync && uv tool install .`
- **Run Eval:** `pitlane run examples/simple-codegen-eval.yaml`
- **Test:** `uv run pytest`
- **Pre-commit:** `uv run pre-commit run --all-files`

## Detailed Guidelines

For specific guidance, see:

- [Development Conventions](.agents/development.md) - TDD workflow, code quality, testing
- [YAML Configuration](.agents/yaml-config.md) - Benchmark structure, assertions
- [Adapter Implementation](.agents/adapters.md) - Creating new assistant adapters
- [Architecture & Design](.agents/architecture.md) - Key decisions, project structure
