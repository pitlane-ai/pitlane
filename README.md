# agent-eval

Lightweight harness to evaluate AI coding assistants against the same task set.

## Install

```bash
uv sync
```

Add `agent-eval` to your PATH:

```bash
uv tool install .
```

This installs the `agent-eval` CLI so you can run it without `uv run`.

## Quickstart

```bash
agent-eval run examples/simple-codegen-eval.yaml
```

## Config Format

Top-level keys:
- `assistants`: mapping of assistant names to config.
- `tasks`: list of task definitions.

See `examples/simple-codegen-eval.yaml` and `examples/terraform-module-eval.yaml` for full examples.

## Schema Generation

Generate the JSON Schema + docs from Pydantic:

```bash
uv run agent-eval schema
```

This writes:
- `schemas/agent-eval.schema.json`
- `docs/schema.md`

## VS Code: YAML Validation with Schema

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
