# agent-eval

Build a skill or MCP? Use `agent-eval` to measure if it works and who it helps.
`agent-eval` provides a repeatable harness for evaluating skill/MCP changes across assistants.
It runs your YAML-defined tasks, checks assertions, and produces a report with pass rates plus practical metrics like wall-clock time, token usage, tool calls, cost (when available), and file/line changes.

## Why this exists

`agent-eval` makes it easy to build your own benchmark and run it in a TDD loop (red, green, refactor) against common AI assistants. It focuses on two goals:
- Simplify creating skills/MCP-based tasks so you can iterate quickly on what "good" looks like.
- Compare performance across assistants in a consistent, repeatable way.

## Install

Install once so running repeated red/green cycles is fast and frictionless.

```bash
uv sync
```

Add `agent-eval` to your PATH:

```bash
uv tool install .
```

This installs the `agent-eval` CLI so you can run it without `uv run`.

## Quickstart

Run a single YAML-defined benchmark to get an immediate, comparable result across assistants.

```bash
agent-eval run examples/simple-codegen-eval.yaml
```

Outputs are written to `runs/` by default and include `results.json`, `meta.yaml`, `debug.log`, and an HTML report.

### Debug Output

Every run creates `debug.log` with command execution details. Add `--verbose` (or `-v`) to also stream output to terminal.

## Config Format

Keep benchmarks as plain YAML so you can diff, review, and iterate quickly.

Top-level keys:
- `assistants`: mapping of assistant names to config.
- `tasks`: list of task definitions.

See `examples/simple-codegen-eval.yaml` and `examples/terraform-module-eval.yaml` for full examples.

### Assistants

An assistant entry tells `agent-eval` how to run a model. Each assistant has:
- `adapter`: which runner to use (e.g. `claude-code`, `codex`).
- `args`: adapter-specific settings (often the model name).
- `skills`: optional list of skills (based on the specs at agentskills.io) or MCP sources to inject for that assistant.

Use multiple assistants to compare baseline vs skill-augmented behavior side by side.

### Tasks

Each task defines the prompt, workspace, and assertions. Minimal shape:
- `name`
- `prompt`
- `workdir` (fixture directory to run in)
- `timeout`
- `assertions` (file checks, command checks, or similarity metrics)

Short task design tips:
- Prefer deterministic assertions (file checks and commands) to keep runs stable.
- Use similarity metrics when exact text is not required.
- Keep workdirs small and focused so red/green loops stay fast.

### TDD Loop

The intended workflow is to treat your eval like a test suite:
1. Red: add or tighten assertions that capture the behavior you want.
2. Green: update skills or MCP sources until the assertions pass.
3. Refactor: clean prompts, tasks, and fixtures without changing outcomes.

## Schema Generation

The schema makes custom benchmark configs safer to edit and easier to validate.

Generate the JSON Schema + docs from Pydantic:

```bash
uv run agent-eval schema
```

This writes:
- `schemas/agent-eval.schema.json`
- `docs/schema.md`

## VS Code: YAML Validation with Schema

Wire the schema into your editor to catch errors early in the loop.

Map the schema in `.vscode/settings.json`:

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

Per-file schema (optional):

```yaml
# yaml-language-server: $schema=./schemas/agent-eval.schema.json
```
