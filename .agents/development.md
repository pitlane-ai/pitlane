# Development Conventions

## Using pitlane for AI Assistant Development

The tool enables TDD-style development of AI assistant capabilities:

1. **Red**: Create YAML benchmark with assertions for desired assistant behavior
2. **Green**: Develop/refine skills or MCP servers until assertions pass
3. **Refactor**: Improve prompts, skills, and configurations without changing outcomes

## Setup

```bash
make        # installs deps, pitlane CLI, and pre-commit hooks
```

## Testing

| Command | Scope |
|---|---|
| `make test` | Fast unit tests only (no integration, no e2e) |
| `make test-all` | Unit + integration — the CI gate |
| `make coverage` | Unit + integration with HTML coverage report |
| `make e2e` | E2E against real AI assistants (requires CLIs installed) |
| `make e2e-claude_code` | E2E for a single adapter |

Test markers:

- `integration` — slow tests that shell out to real tools (npx, etc.), run in CI but not pre-commit
- `e2e` — tests that invoke real AI assistants, on-demand only

## Code Quality

- Use type hints (Python 3.11+ syntax)
- Leverage Pydantic for configuration validation
- Document adapter-specific behavior and limitations
- **Testing**: Favour `pytest-mock` over `unittest.mock` for consistency

## Benchmark Design

- Keep fixtures small and focused for fast iteration
- Prefer deterministic assertions over similarity metrics when possible
- Store fixtures in `examples/fixtures/`
