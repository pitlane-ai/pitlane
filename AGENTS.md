# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview

`agent-eval` is a lightweight Python-based evaluation harness for AI coding assistants. It provides a repeatable framework for measuring the effectiveness of skills, MCP (Model Context Protocol) servers, and assistant configurations across different AI coding assistants.

**Core Purpose**: Enable TDD-style development of AI assistant capabilities by providing:
- YAML-based benchmark definitions for easy iteration
- Consistent evaluation across multiple assistants (Claude Code, Codex, Cline, Mistral Vibe, OpenCode)
- Deterministic and similarity-based assertions
- Comprehensive metrics (wall-clock time, token usage, cost, file/line changes)
- HTML reports for result visualization

**Technology Stack**:
- Python 3.11+
- Typer for CLI
- Pydantic for configuration validation
- YAML for benchmark definitions
- Jinja2 for HTML report generation
- HuggingFace evaluate, sentence-transformers, BERT-score for similarity metrics

**Architecture**:
- `cli.py`: Command-line interface (run, report, init, schema)
- `config.py`: YAML configuration loading and validation
- `runner.py`: Orchestrates evaluation execution
- `adapters/`: Assistant-specific implementations (claude_code, codex, cline, mistral_vibe, opencode)
- `assertions/`: Evaluation logic (deterministic file/command checks, similarity metrics)
- `reporting/`: HTML report generation
- `workspace.py`: Manages isolated test environments
- `metrics.py`: Tracks and aggregates performance metrics

## Building and Running

### Installation

Install dependencies and the CLI tool:

```bash
# Install dependencies
uv sync

# Install CLI globally
uv tool install .
```

### Running Evaluations

Execute a benchmark configuration:

```bash
# Run all tasks and assistants
agent-eval run examples/simple-codegen-eval.yaml

# Run specific task
agent-eval run examples/simple-codegen-eval.yaml --task hello-world-python

# Run specific assistant
agent-eval run examples/simple-codegen-eval.yaml --assistant claude-baseline

# Custom output directory
agent-eval run examples/simple-codegen-eval.yaml --output-dir my-runs
```

### Other Commands

```bash
# Initialize new eval project
agent-eval init

# Generate JSON Schema and documentation
agent-eval schema

# Regenerate HTML report from previous run
agent-eval report runs/2024-01-01_12-00-00
```

### Testing

```bash
# Run test suite
uv run pytest

# Run specific test file
uv run pytest tests/test_assertions.py
```

## Development Conventions

### TDD Workflow

The project is designed around a red-green-refactor loop:

1. **Red**: Add or tighten assertions that capture desired behavior
2. **Green**: Update skills/MCP sources until assertions pass
3. **Refactor**: Clean prompts, tasks, and fixtures without changing outcomes

### YAML Configuration Structure

Benchmark configs follow this pattern:

```yaml
assistants:
  assistant-name:
    adapter: claude-code|codex|cline|mistral-vibe|opencode
    args:
      model: model-name
      # adapter-specific args
    skills: []  # optional skill/MCP sources

tasks:
  - name: task-name
    prompt: "Task description"
    workdir: ./fixtures/directory
    timeout: 120
    assertions:
      - file_exists: "filename"
      - command_succeeds: "command"
      - file_contains:
          file: "filename"
          pattern: "regex"
      - bleu:
          reference_file: "expected.txt"
          candidate_file: "actual.txt"
          threshold: 0.5
```

### Assertion Types

**Deterministic** (preferred for stability):
- `file_exists`: Check file presence
- `file_contains`: Regex pattern matching in files
- `command_succeeds`: Command exits with 0
- `command_fails`: Command exits with non-zero

**Similarity-based** (when exact matching isn't feasible):
- `bleu`: BLEU score comparison
- `rouge`: ROUGE score comparison
- `bertscore`: BERT-based semantic similarity
- `cosine_similarity`: Embedding cosine similarity

### Adapter Implementation

When adding new adapters:
1. Inherit from `BaseAdapter` in `adapters/base.py`
2. Implement `cli_name()`, `agent_type()`, and `run()` methods
3. Return `AdapterResult` with conversation, token_usage, and cost_usd
4. Parse assistant-specific output formats into standardized structure
5. Handle timeouts gracefully

### Code Quality

- Use type hints throughout (Python 3.11+ syntax)
- Follow Pydantic patterns for configuration validation
- Keep fixtures small and focused for fast iteration
- Prefer deterministic assertions over similarity metrics
- Document adapter-specific behavior and limitations

### Project Structure Principles

- Keep benchmark definitions as plain YAML for easy diffing
- Store fixtures in `examples/fixtures/` or `fixtures/`
- Write run outputs to `runs/` by default
- Generate schema and docs from Pydantic models (single source of truth)
- Support VS Code YAML validation via JSON Schema

### Key Design Decisions

- **Subprocess-based execution**: Each adapter runs as a subprocess for isolation
- **Stream-based parsing**: Parse NDJSON/streaming output for real-time metrics
- **Workspace isolation**: Each task runs in a clean workspace copy
- **Exit code semantics**: CLI exits non-zero if any assertion fails
- **Metric collection**: Track wall-clock time, tokens, cost, and file changes consistently

## VS Code Integration

Enable YAML validation by adding to `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "./schemas/agent-eval.schema.json": [
      "eval.yaml",
      "examples/*.yaml",
      "**/*eval*.y*ml"
    ]
  },
  "yaml.validate": true
}
```
