# pitlane 🏁

[![CI](https://github.com/vburckhardt/pitlane/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/vburckhardt/pitlane/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/vburckhardt/pitlane/branch/main/graph/badge.svg)](https://codecov.io/gh/vburckhardt/pitlane)
[![PyPI version](https://badge.fury.io/py/pitlane.svg)](https://badge.fury.io/py/pitlane)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](CONTRIBUTING.md)

> A feedback loop for people building AI coding skills and MCP servers.

You're building a skill, an MCP server, or a custom prompt strategy that's supposed to make an AI coding assistant better at a specific job. But how do you know it actually works? How do you know your latest commit made things better and not worse?

Pitlane gives you the answer. Define the tasks your skill should help with, set up a baseline (assistant without your skill) and a challenger (assistant with your skill), and race them. The results tell you with numbers, not vibes, whether your work is paying off.

## The idea

In motorsport, the pit lane is where engineers tune the car between laps. Swap a part, adjust the setup, check the telemetry, see if the next lap is faster.

Building skills and MCP servers works the same way:

1. Tune: change your skill, update your MCP server, tweak your prompts
2. Race: run the assistant with and without your changes against real coding tasks
3. Check the telemetry: did pass rates go up? Did quality improve? Did it get faster or cheaper?
4. Repeat: go back to the pit, make another adjustment, race again

Pitlane is the telemetry system. You build the skill, pitlane tells you if it's working.

## Key features

- YAML-based benchmark definitions (easy to version and diff)
- Deterministic assertions (file checks, command execution, custom scripts)
- Similarity metrics (ROUGE, BLEU, BERTScore, cosine similarity)
- Metrics tracking (time, tokens, cost, file changes)
- JUnit XML output (`junit.xml`) for native CI test reporting
- Interactive HTML reports with side-by-side agent comparison
- Parallel execution and repeated runs with statistics
- Graceful interrupt handling (Ctrl+C generates partial reports)
- TDD workflow support (red-green-refactor)

## Table of Contents

- [Quick Start](#quick-start)
- [Supported Assistants](#supported-assistants)
- [Usage](#usage)
- [Writing Benchmarks](#writing-benchmarks)
- [TDD Workflow](#tdd-workflow)
- [Editor Integration](#editor-integration)
- [Contributing](#contributing)
- [License](#license)

## Quick start

Requires [uv](https://github.com/astral-sh/uv), a fast Python package installer. Install it with:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

The example uses [OpenCode](https://opencode.ai) because it's free and requires no API key. Install it first, then:

```bash
uv tool install pitlane --from git+https://github.com/vburckhardt/pitlane.git
pitlane init --with-examples
pitlane run pitlane/examples/simple-codegen-eval.yaml
```

Results appear in `runs/` with an HTML report showing pass rates and metrics across all assistants.

Any [supported assistant](#supported-assistants) works — edit `pitlane/examples/simple-codegen-eval.yaml` to uncomment others, or pass `--assistant <name>` to target one you already have installed.

To run without installing: `uvx --from git+https://github.com/vburckhardt/pitlane.git pitlane run pitlane/examples/simple-codegen-eval.yaml`

## Supported assistants

| Assistant | Adapter Name | Status |
|-----------|--------------|--------|
| [Bob](https://www.ibm.com/products/bob) | `bob` | ✅ Tested |
| [Claude Code](https://www.anthropic.com/claude) | `claude-code` | ✅ Tested |
| [Mistral Vibe](https://mistral.ai/) | `mistral-vibe` | ✅ Tested |
| [OpenCode](https://opencode.ai) | `opencode` | ✅ Tested |

**Want to add support for another assistant?** See the [Contributing Guide](CONTRIBUTING.md#adding-a-new-adapter) for instructions on implementing new adapters.

## Usage

### Basic Evaluation

Run all tasks against all configured assistants:

```bash
pitlane run examples/simple-codegen-eval.yaml
```

### Filtering

Run specific tasks or assistants:

```bash
# Single task
pitlane run examples/simple-codegen-eval.yaml --task hello-world-python

# Single assistant
pitlane run examples/simple-codegen-eval.yaml --assistant claude-baseline

# Combine filters
pitlane run examples/simple-codegen-eval.yaml --task hello-world-python --assistant claude-baseline
```

### Parallel execution

Speed up multi-task benchmarks:

```bash
pitlane run examples/simple-codegen-eval.yaml --parallel 4
```

### Repeated runs

Run tasks multiple times to measure consistency and get aggregated statistics:

```bash
pitlane run examples/simple-codegen-eval.yaml --repeat 5
```

This runs each task 5 times and reports avg/min/max/stddev for all metrics in the HTML report.

### Debug output

Every run creates `debug.log` with detailed execution information. Stream output to terminal in real-time:

```bash
pitlane run examples/simple-codegen-eval.yaml --verbose
```

All assertions include detailed logging to help diagnose failures.

### Interrupt handling

Press Ctrl+C to stop a run. You'll get a partial HTML report with results from completed tasks.

### Open report in browser

Add `--open` to launch `report.html` in your default browser immediately after the run:

```bash
pitlane run examples/simple-codegen-eval.yaml --open
```

The same flag works when regenerating a report:

```bash
pitlane report runs/2024-01-01_12-00-00 --open
```

### Other commands

```bash
# Initialize new benchmark project
pitlane init

# Initialize with example benchmarks
pitlane init --with-examples

# Generate JSON Schema for YAML validation
pitlane schema generate

# Install VS Code YAML validation (safe, with preview)
pitlane schema install

# Regenerate HTML report from existing junit.xml
pitlane report runs/2024-01-01_12-00-00
```

## Writing benchmarks

Benchmarks are YAML files with two sections: `assistants` and `tasks`.

### Minimal example

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

### Custom script assertions

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

### Similarity assertions

#### Similarity metrics

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

#### Weighted grading

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

The `examples/` directory contains working benchmarks you can use as starting points:

- **`simple-codegen-eval.yaml`** — Minimal example with deterministic assertions
- **`similarity-codegen-eval.yaml`** — Demonstrates all similarity metrics
- **`terraform-module-eval.yaml`** — Real-world Terraform evaluation
- **`weighted-grading-eval.yaml`** — Weighted assertions and continuous scoring

## TDD workflow

Treat benchmarks like tests:

1. **Red**: Add or tighten assertions
2. **Green**: Update skills/MCP until assertions pass
3. **Refactor**: Clean up without breaking tests

This lets you iterate on what "good" means without guessing.

## Editor integration

### VS Code / Cursor / Bob

Enable YAML validation:

```bash
pitlane schema install
```

This adds JSON Schema validation to `.vscode/settings.json` with preview and backup.

Manual setup:

```json
{
  "yaml.schemas": {
    "./pitlane/schemas/pitlane.schema.json": [
      "eval.yaml",
      "examples/*.yaml",
      "**/*eval*.y*ml"
    ]
  },
  "yaml.validate": true
}
```

### Other editors

Generate schema and docs:

```bash
pitlane schema generate
```

Outputs:

- `pitlane/schemas/pitlane.schema.json`
- `pitlane/docs/schema.md`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and how to submit changes.

## License

Apache 2.0
