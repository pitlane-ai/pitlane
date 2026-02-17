# Contributing to pitlane

This guide covers development setup, testing, and how to submit changes.

## Getting started

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Development setup

1. Fork and clone the repository:

```bash
git clone https://github.com/vburckhardt/pitlane.git
cd pitlane
```

2. Install dependencies:

```bash
uv sync
```

3. Install the CLI in development mode:

   ```bash
   uv tool install .
   ```

4. Install pre-commit hooks:

   ```bash
   uv run pre-commit install
   ```

   This will automatically run code quality checks before each commit.

## Running tests

Run the full test suite:

```bash
uv run pytest
```

Run specific test files:

```bash
uv run pytest tests/test_assertions.py
```

Skip slow integration tests:

```bash
uv run pytest -m "not integration"
```

Run tests with coverage:

```bash
uv run pytest --cov=src/pitlane --cov-report=html
```

## Adding new features

### Adding a new adapter

We currently support Claude Code, Mistral Vibe, and OpenCode. To add support for a new AI coding assistant:

1. Create `src/pitlane/adapters/your_adapter.py`
2. Inherit from `BaseAdapter` in `adapters/base.py`
3. Implement required methods:
   - `cli_name()` - Returns the CLI identifier
   - `agent_type()` - Returns the agent type string
   - `run()` - Executes the assistant and returns results
4. Return `AdapterResult` with:
   - `conversation` - List of message exchanges
   - `token_usage` - Token counts (if available)
   - `cost_usd` - Estimated cost (if available)
5. Add comprehensive tests in `tests/test_adapter_your_adapter.py`
6. Update the adapter registry in `adapters/__init__.py`
7. Add the adapter to the supported assistants table in README.md

Example adapter structure:

```python
from pitlane.adapters.base import BaseAdapter, AdapterResult

class YourAdapter(BaseAdapter):
    @staticmethod
    def cli_name() -> str:
        return "your-assistant"

    @staticmethod
    def agent_type() -> str:
        return "YourAssistant"

    def run(self, task_prompt: str, workdir: Path, timeout: int) -> AdapterResult:
        # Implementation here
        pass
```

See existing adapters for complete examples.

### Adding new assertion types

1. Add the assertion logic to `src/pitlane/assertions/deterministic.py` or `similarity.py`
2. Update the dispatcher in `evaluate_assertion()`
3. Add the assertion type to the config schema in `src/pitlane/config.py`
4. Add tests in `tests/test_assertions.py`
5. Update documentation in README.md

### Adding new similarity metrics

1. Add the metric implementation to `src/pitlane/assertions/similarity.py`
2. Update `evaluate_similarity_assertion()` to handle the new metric
3. Add tests with known reference/candidate pairs
4. Document when to use the metric in README.md

## Code style

- Use type hints throughout (Python 3.11+ syntax)
- Follow PEP 8 style guidelines
- Use Pydantic models for configuration validation
- Keep functions focused and testable
- Add docstrings for public APIs

### Pre-commit hooks

The project uses pre-commit hooks to ensure code quality. These run automatically before each commit if you installed them (see setup step 4).

Run all checks manually:

```bash
uv run pre-commit run --all-files
```

The pre-commit hooks include:

- Ruff linting and formatting
- mypy type checking
- pytest (fast tests only)
- YAML validation
- Markdown linting
- Secret detection
- File quality checks (trailing whitespace, end-of-file fixes, etc.)

## Testing guidelines

- Write tests for all new functionality
- Use fixtures in `tests/conftest.py` for common test data
- Mock external dependencies (file system, subprocess calls)
- Test both success and failure cases
- Keep tests fast (mock slow operations)

## Submitting changes

1. Create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and add tests

3. Run tests:

   ```bash
   uv run pytest
   ```

4. Commit with a clear message:

   ```bash
   git commit -m "feat: add support for new assistant"
   ```

   Use conventional commit prefixes:

   - `feat:` - New features
   - `fix:` - Bug fixes
   - `docs:` - Documentation changes
   - `test:` - Test additions or changes
   - `refactor:` - Code refactoring
   - `chore:` - Maintenance tasks

5. Push to your fork:

   ```bash
   git push origin feature/your-feature-name
   ```

6. Open a pull request on GitHub

## Pull request guidelines

- Describe what your PR does and why
- Reference related issues
- Include test coverage for new code
- Update docs if needed
- Keep PRs focused on one change

## Questions?

Open an issue or start a discussion on GitHub.
