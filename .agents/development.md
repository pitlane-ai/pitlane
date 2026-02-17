# Development Conventions

## Using pitlane for AI Assistant Development

The tool enables TDD-style development of AI assistant capabilities:

1. **Red**: Create YAML benchmark with assertions for desired assistant behavior
2. **Green**: Develop/refine skills or MCP servers until assertions pass
3. **Refactor**: Improve prompts, skills, and configurations without changing outcomes

## Code Quality

- Use type hints (Python 3.11+ syntax)
- Leverage Pydantic for configuration validation
- Document adapter-specific behavior and limitations

## Benchmark Design

- Keep fixtures small and focused for fast iteration
- Prefer deterministic assertions over similarity metrics when possible
- Store fixtures in `examples/fixtures/`
