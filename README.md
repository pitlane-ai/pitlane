# agent-eval

A lightweight evaluation harness for AI coding assistants. Define benchmarks in YAML, run them across multiple assistants, and get comparable metrics on what works.

## What It Does

`agent-eval` lets you test whether your skills, MCP servers, or prompts actually improve AI assistant performance. Write a benchmark once, run it against Claude Code, Codex, Cline, Mistral Vibe, or OpenCode, and see which configurations perform best.

**Key features:**
- YAML-based benchmark definitions (easy to version and diff)
- Deterministic assertions (file checks, command execution, custom scripts)
- Similarity metrics (ROUGE, BLEU, BERTScore, cosine similarity)
- Comprehensive metrics (time, tokens, cost, file changes)
- HTML reports with side-by-side comparisons
- Parallel execution and repeated runs with statistics
- Graceful interrupt handling (Ctrl+C generates partial reports)
- TDD workflow support (red-green-refactor)

## Quick Start

Install dependencies:

```bash
uv sync
uv tool install .
```

Run your first benchmark:

```bash
agent-eval run examples/simple-codegen-eval.yaml
```

Results appear in `runs/` with an HTML report showing pass rates and metrics across all assistants.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- One or more AI coding assistants installed

## Installation

### Using uv (recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/agent-eval.git
cd agent-eval

# Install dependencies
uv sync

# Install CLI globally
uv tool install .
```

### Using pip

```bash
pip install -e .
```

## Usage

### Basic Evaluation

Run all tasks against all configured assistants:

```bash
agent-eval run examples/simple-codegen-eval.yaml
```

### Filtering

Run specific tasks or assistants:

```bash
# Single task
agent-eval run examples/simple-codegen-eval.yaml --task hello-world-python

# Single assistant
agent-eval run examples/simple-codegen-eval.yaml --assistant claude-baseline

# Combine filters
agent-eval run examples/simple-codegen-eval.yaml --task hello-world-python --assistant claude-baseline
```

### Parallel Execution

Speed up multi-task benchmarks:

```bash
agent-eval run examples/simple-codegen-eval.yaml --parallel 4
```

### Repeated Runs

Run tasks multiple times to measure consistency and get aggregated statistics:

```bash
agent-eval run examples/simple-codegen-eval.yaml --repeat 5
```

This runs each task 5 times and reports avg/min/max/stddev for all metrics in the HTML report.

### Debug Output

Every run creates `debug.log` with detailed execution information. Stream output to terminal in real-time:

```bash
agent-eval run examples/simple-codegen-eval.yaml --verbose
```

All assertions include detailed logging to help diagnose failures.

### Interrupt Handling

Press Ctrl+C to stop a run. You'll get a partial HTML report with results from completed tasks.

### Other Commands

```bash
# Initialize new benchmark project
agent-eval init

# Generate JSON Schema for YAML validation
agent-eval schema generate

# Install VS Code YAML validation (safe, with preview)
agent-eval schema install

# Regenerate HTML report from previous run
agent-eval report runs/2024-01-01_12-00-00
```

## Writing Benchmarks

Benchmarks are YAML files with two sections: `assistants` and `tasks`.

### Minimal Example

```yaml
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: haiku

tasks:
  - name: hello-world-python
    prompt: "Create a Python script called hello.py that prints 'Hello, World!'"
    workdir: ./fixtures/empty
    timeout: 120
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "python hello.py"
      - file_contains: { path: "hello.py", pattern: "Hello, World!" }
```

### Assistants

Each assistant defines how to run a model:

```yaml
assistants:
  # Baseline configuration
  claude-baseline:
    adapter: claude-code
    args:
      model: haiku

  # With skills/MCP
  claude-with-skill:
    adapter: claude-code
    args:
      model: haiku
    skills:
      - source: org/repo
        skill: my-skill-name
```

**Available adapters:** `claude-code`, `codex`, `cline`, `mistral-vibe`, `opencode`

Run `agent-eval run --help` to see all adapters.

### Tasks

Each task specifies:
- `name`: Unique identifier
- `prompt`: Instructions for the assistant
- `workdir`: Fixture directory (copied for each run)
- `timeout`: Maximum seconds
- `assertions`: Checks to verify success

### Assertions

#### Deterministic (preferred)

```yaml
assertions:
  # File exists
  - file_exists: "main.py"
  
  # Command succeeds (exit code 0)
  - command_succeeds: "python main.py"
  
  # Command fails (non-zero exit)
  - command_fails: "python main.py --invalid"
  
  # File contains pattern (regex)
  - file_contains:
      path: "main.py"
      pattern: "def main\\(\\):"
  
  # Custom script validation
  - custom_script:
      script: "./validate.sh"
      interpreter: "bash"
      timeout: 30
      expected_exit_code: 0
```

### Custom Script Assertions

When you need more complex validation logic than simple commands provide, use `custom_script` to run a dedicated test script. This is useful for multi-step validation, complex parsing, or reusable test logic.

**Simple form** (expects exit code 0):
```yaml
- custom_script: "scripts/validate_output.sh"
- custom_script: "python scripts/validate.py"
- custom_script: "node scripts/check.js"
```

**Advanced form** with options:
```yaml
- custom_script:
    script: "python scripts/validate_output.py"
    args: ["--strict", "--format=json"]
    timeout: 30
    expected_exit_code: 0
```

**Options:**
- `script` — Shell command to execute (e.g., `python script.py`, `node script.js`, `./script.sh`)
- `args` — List of arguments to pass to the script (optional)
- `timeout` — Maximum seconds to wait for completion (default: 60)
- `expected_exit_code` — Exit code that indicates success (default: 0)

The `script` field is executed as a shell command in the workdir, so you can use any interpreter:
- **Python:** `python validate.py` or `python3 validate.py`
- **Node.js:** `node check.js`
- **Executable scripts:** `./validate.sh` (must have shebang and be executable)
- **Any command:** Works like `command_succeeds` but with more control over timeout and exit codes

Your script receives the workdir as its working directory, so it can access generated files directly. The assertion passes if the script exits with the expected code.

**Example validation script** (`scripts/validate_tf.sh`):
```bash
#!/bin/bash
# Check if Terraform config is valid and contains required resources
terraform validate || exit 1
grep -q "aws_s3_bucket" main.tf || exit 2
exit 0
```

Use it in your eval:
```yaml
- custom_script: "scripts/validate_tf.sh"
```

### Similarity Assertions

#### Similarity Metrics

When exact matching isn't practical, use similarity metrics:

```yaml
assertions:
  # ROUGE: topic coverage (good for docs)
  - rouge:
      actual: "README.md"
      expected: "./refs/golden.md"
      metric: "rougeL"
      min_score: 0.35
  
  # BLEU: phrase matching (good for docs, not code)
  - bleu:
      actual: "README.md"
      expected: "./refs/golden.md"
      min_score: 0.2
  
  # BERTScore: semantic similarity (good for docs/code)
  - bertscore:
      actual: "README.md"
      expected: "./refs/golden.md"
      min_score: 0.75
  
  # Cosine similarity: overall meaning (good for code/configs)
  - cosine_similarity:
      actual: "variables.tf"
      expected: "./refs/expected-vars.tf"
      min_score: 0.7
```

**Choosing metrics:**

| Metric | Question | Speed | Best For |
|--------|----------|-------|----------|
| `rouge` | Same topics? | Fast | Documentation coverage |
| `bleu` | Same phrases? | Fast | Documentation phrasing |
| `bertscore` | Same meaning? | Slow | Semantic preservation |
| `cosine_similarity` | Same subject? | Slow | Code/config similarity |

Use deterministic assertions first. Add similarity metrics when you need fuzzy matching.

#### Weighted Grading

Make some assertions count more:

```yaml
assertions:
  - file_exists: "main.tf"
  - command_succeeds: "terraform validate"
    weight: 3.0  # 3x more important
  - rouge:
      actual: "README.md"
      expected: "./refs/golden.md"
      metric: "rougeL"
      min_score: 0.3
    weight: 2.0
```

Results include both `assertion_pass_rate` (binary) and `weighted_score` (continuous).

See `examples/weighted-grading-eval.yaml` for details.

## Examples

The `examples/` directory contains working benchmarks:

- **`simple-codegen-eval.yaml`** — Minimal example with deterministic assertions
- **`similarity-codegen-eval.yaml`** — Demonstrates all similarity metrics
- **`terraform-module-eval.yaml`** — Real-world Terraform evaluation
- **`weighted-grading-eval.yaml`** — Weighted assertions and continuous scoring

## TDD Workflow

Treat benchmarks like tests:

1. **Red**: Add or tighten assertions
2. **Green**: Update skills/MCP until assertions pass
3. **Refactor**: Clean up without breaking tests

This lets you iterate on what "good" means without guessing.

## Editor Integration

### VS Code / Cursor / Bob

Enable YAML validation:

```bash
agent-eval schema install
```

This adds JSON Schema validation to `.vscode/settings.json` with preview and backup.

Manual setup:

```json
{
  "yaml.schemas": {
    "./agent-eval/schemas/agent-eval.schema.json": [
      "eval.yaml",
      "examples/*.yaml",
      "**/*eval*.y*ml"
    ]
  },
  "yaml.validate": true
}
```

### Other Editors

Generate schema and docs:

```bash
agent-eval schema generate
```

Outputs:
- `agent-eval/schemas/agent-eval.schema.json`
- `agent-eval/docs/schema.md`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and how to submit changes.

## License

Apache 2.0
