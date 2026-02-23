# Contributing to pitlane

This guide covers development setup, testing, and how to submit changes.

## Getting started

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Git
- `make`

### Development setup

1. Fork and clone the repository:

```bash
git clone https://github.com/vburckhardt/pitlane.git
cd pitlane
```

2. Run setup:

```bash
make
```

This installs dependencies, the pitlane CLI, and the pre-commit hooks in one step.

## Running tests

| Command | What it runs |
|---|---|
| `make test` | Fast unit tests only |
| `make test-all` | Unit + integration (the CI gate) |
| `make coverage` | Unit + integration with HTML coverage report |
| `make e2e` | E2E tests against real AI assistants (requires CLIs installed) |
| `make e2e-claude_code` | E2E tests for a single adapter |

Run a specific test file:

```bash
uv run pytest tests/test_assertions.py
```

### E2E tests

E2E tests invoke real AI assistants and are excluded from CI and pre-commit. Run them
on-demand once all relevant CLIs are installed:

```bash
make e2e
```

If a required CLI is missing the test fails immediately with a clear message — it does
not skip silently.

## Adding new features

### Adding a new adapter

1. Create `src/pitlane/adapters/your_adapter.py`
2. Inherit from `BaseAdapter` in `adapters/base.py`
3. Implement all five required methods:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

from pitlane.adapters.base import AdapterResult, BaseAdapter

if TYPE_CHECKING:
    import logging
    from pitlane.config import McpServerConfig


class YourAdapter(BaseAdapter):
    def cli_name(self) -> str:
        return "your-cli"

    def agent_type(self) -> str:
        return "your-adapter"

    def get_cli_version(self) -> str | None:
        import subprocess
        try:
            result = subprocess.run(
                ["your-cli", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def install_mcp(self, workspace: Path, mcp: McpServerConfig) -> None:
        # Write MCP server config into the workspace directory
        pass

    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> AdapterResult:
        # Execute the assistant and return results
        pass
```

`AdapterResult` fields:

```python
AdapterResult(
    stdout="",                      # raw stdout from the CLI
    stderr="",                      # raw stderr from the CLI
    exit_code=0,                    # process exit code
    duration_seconds=1.5,           # wall-clock time
    conversation=[                  # parsed message list
        {"role": "assistant", "content": "..."}
    ],
    token_usage={"input": 100, "output": 50},  # None if unavailable
    cost_usd=0.001,                 # None if unavailable
    tool_calls_count=3,             # None if unavailable
    timed_out=False,
)
```

4. Register the adapter in `src/pitlane/adapters/__init__.py`:

```python
from .your_adapter import YourAdapter

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    ...
    "your-adapter": YourAdapter,
}
```

5. Add it to the `AdapterType` enum in `src/pitlane/config.py`:

```python
class AdapterType(str, Enum):
    ...
    YOUR_ADAPTER = "your-adapter"
```

6. Add tests in `tests/test_adapter_your_adapter.py`
7. Add E2E smoke tests in `tests/test_e2e_adapters.py`
8. Add the adapter to the supported assistants table in README.md

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

### Pre-commit hooks

Pre-commit hooks run automatically before each commit. Run them manually:

```bash
make pre-commit
```

The hooks include ruff linting and formatting, mypy type checking, fast pytest, YAML
validation, markdown linting, and secret detection.

To run just lint and type checks without tests:

```bash
make check
```

## Testing guidelines

- Write tests for all new functionality
- Mock `run_streaming_sync` for adapter unit tests — never the adapter itself
- Test both success and failure cases including timeouts and malformed output
- Keep unit tests fast (no real subprocess calls)
- Add an E2E class in `tests/test_e2e_adapters.py` for any new adapter

## Submitting changes

1. Create a feature branch:

```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and add tests

3. Run the full check:

```bash
make check
make test-all
```

4. Commit with a conventional commit message:

```bash
git commit -m "feat: add support for new assistant"
```

Prefixes: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

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
