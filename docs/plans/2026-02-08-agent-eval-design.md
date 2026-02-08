# agent-eval: AI Assistant Evaluation Harness

## Overview

`agent-eval` is a lightweight Python CLI tool that evaluates the performance of AI coding assistants (Claude Code, Codex, Mistral Vibe, and others) by running them against the same tasks and comparing results side by side.

### Goals

1. **Validate that skills/MCP improve outcomes** — TDD-style: run baseline (no skills) → add skills → compare. Red/green/refactor loop for skill development.
2. **Guide skill/MCP iteration** — Quantify whether changes are moving in the right direction.
3. **Compare assistants** — Same prompt, same config, side-by-side HTML report showing which assistant performs better for a given task.

### Non-Goals

- No web UI or IDE integration — CLI only
- No real-time monitoring — batch eval runs only
- No LLM-as-judge in v1 (designed for later addition)

## Architecture

Three phases: **configure → run → report**.

```
eval.yaml → Runner → Adapters → Assertions → Metrics → HTML Report
```

### Core Concepts

- **Eval file** (YAML): defines assistants and tasks
- **Adapter**: drives a specific CLI assistant via subprocess
- **Task**: a prompt + working directory + assertions
- **Assertion**: a pass/fail check on the workspace after an assistant completes
- **Run**: one execution of all tasks against all assistants, stored in a timestamped directory

## Eval File Format

```yaml
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet

  claude-with-skills:
    adapter: claude-code
    args:
      model: sonnet
      mcp_config: ./mcp-servers.json
      skills: ["terraform-ibm-modules-solution-builder"]

  codex-baseline:
    adapter: codex
    args:
      model: o3

  vibe-baseline:
    adapter: mistral-vibe
    args:
      model: devstral-2

tasks:
  - name: scaffold-terraform-module
    prompt: "Create a Terraform module for an IBM VPC with 3 subnets"
    workdir: ./fixtures/empty-repo
    timeout: 300
    assertions:
      - file_exists: "main.tf"
      - file_exists: "variables.tf"
      - file_contains: { path: "main.tf", pattern: "resource.*ibm_is_vpc" }
      - command_succeeds: "terraform validate"
      - rouge: { actual: "README.md", expected: "./refs/expected-readme.md", metric: "rougeL", min_score: 0.5 }
```

### Key Design Choice: Multiple Profiles per Adapter

The same adapter can appear multiple times with different configs. This lets you compare `claude-baseline` vs `claude-with-skills` in the same run — making it immediately visible whether skills help.

### Typical Workflow

```
1. Write eval.yaml with tasks + assertions
2. agent-eval run eval.yaml                # Baseline: no skills/MCP
3. Results may already pass (LLM has the knowledge)
4. Add skills/MCP config to assistant entries
5. agent-eval run eval.yaml                # Compare: did skills improve?
6. Open report.html — compare baseline vs with-skills
7. Iterate on skills, re-run
```

## Adapter System

Each assistant gets an adapter — a Python class that invokes the CLI as a subprocess and parses output. All adapters implement a common interface:

```python
@dataclass
class AdapterResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    conversation: list[dict]     # parsed messages/tool calls when available
    token_usage: dict | None     # {"input": N, "output": N} if reported
    cost_usd: float | None       # if reported by CLI

class BaseAdapter(ABC):
    @abstractmethod
    def run(self, prompt: str, workdir: Path, config: dict) -> AdapterResult:
        ...
```

### Initial Adapters

**ClaudeCodeAdapter**
```bash
claude -p --output-format json --dangerously-skip-permissions \
  --mcp-config ./mcp.json --model sonnet \
  "Create a Terraform module..."
```
JSON output provides conversation, tool calls, and token usage natively.

**CodexAdapter**
```bash
codex exec --json --yolo -m o3 \
  "Create a Terraform module..."
```
JSON output with final message. Progress streams to stderr.

**MistralVibeAdapter**
```bash
vibe --prompt "Create a Terraform module..." \
  --auto-approve --max-turns 50
```
Text output — adapter parses what it can from stdout/stderr.

### Adding New Adapters

Adding a new assistant means writing one class (~50-80 lines) that implements `run()`. The adapter handles CLI-specific quirks; everything upstream and downstream is generic.

## Assertion System

Two categories: **deterministic** and **similarity**.

### Deterministic Assertions

```yaml
- file_exists: "main.tf"
- file_contains: { path: "main.tf", pattern: "resource.*ibm_is_vpc" }
- command_succeeds: "terraform validate"
- command_fails: "grep -r 'hardcoded_api_key' ."
```

`command_succeeds` is the escape hatch — anything checkable via shell command can be asserted.

### Similarity Assertions

Compare assistant output against a reference file:

```yaml
- bleu: { actual: "README.md", expected: "./refs/expected-readme.md", min_score: 0.6 }
- rouge: { actual: "README.md", expected: "./refs/expected-readme.md", metric: "rougeL", min_score: 0.5 }
- bertscore: { actual: "README.md", expected: "./refs/expected-readme.md", min_score: 0.8 }
- cosine_similarity: { actual: "README.md", expected: "./refs/expected-readme.md", min_score: 0.85 }
```

| Metric | What it measures | Good for |
|--------|-----------------|----------|
| BLEU | n-gram precision overlap | Short, structured text |
| ROUGE-L | Longest common subsequence | Longer text, summaries |
| BERTScore | Semantic similarity via embeddings | Meaning preservation despite different wording |
| Cosine similarity | Embedding distance | Quick semantic "close enough" check |

### Assertion Result

```python
@dataclass
class AssertionResult:
    name: str        # e.g. "file_contains: main.tf ~ resource.*ibm_is_vpc"
    passed: bool
    message: str     # human-readable explanation on failure
```

A task passes only if all its assertions pass.

## Metrics Capture

Every run automatically captures baseline metrics (no configuration needed):

| Metric | Source |
|--------|--------|
| `wall_clock_seconds` | Measured by harness |
| `exit_code` | CLI process exit code |
| `files_created` | Diff of workspace before/after |
| `files_modified` | Diff of workspace before/after |
| `total_lines_generated` | Count from created/modified files |
| `token_usage_input` | Parsed from CLI output (when available) |
| `token_usage_output` | Parsed from CLI output (when available) |
| `cost_usd` | Parsed from CLI output (when available) |
| `tool_calls_count` | Parsed from conversation (when available) |
| `assertion_pass_count` | Computed |
| `assertion_fail_count` | Computed |
| `assertion_pass_rate` | Computed |

## HTML Report

A single self-contained `.html` file (inline CSS/JS, no external dependencies). Three views:

1. **Summary table** — Assistants as columns, tasks as rows. Each cell shows pass/fail, duration, cost, assertion pass rate. Color-coded: green (all pass), yellow (partial), red (all fail).

2. **Task detail** — Click to expand. Shows each assistant's results side by side: assertion results, metrics, collapsible conversation log. Similarity assertions show scores with visual bars.

3. **Metrics comparison** — Bar charts comparing assistants on time, cost, tokens, pass rate. Rendered with inline Chart.js or SVG (no server needed).

Regenerable from raw data:
```bash
agent-eval report runs/2026-02-08_143022/
```

## Run Output Structure

```
runs/
  2026-02-08_143022/
    meta.yaml              # run metadata (timestamp, config used)
    results.json           # structured results for all tasks/assistants
    report.html            # self-contained HTML report
    claude-baseline/
      scaffold-terraform-module/
        conversation.json  # full conversation log
        workspace/         # final state of working directory
    claude-with-skills/
      scaffold-terraform-module/
        ...
    codex-baseline/
      ...
```

## CLI Interface

```bash
# Initialize a new eval project
agent-eval init

# Run all tasks against all assistants
agent-eval run eval.yaml

# Run specific task or assistant only
agent-eval run eval.yaml --task scaffold-terraform-module
agent-eval run eval.yaml --assistant claude-baseline

# Run assistants concurrently per task
agent-eval run eval.yaml --parallel

# Regenerate report from existing run
agent-eval report runs/2026-02-08_143022/

# List past runs
agent-eval runs
```

**Exit codes:** `agent-eval run` exits 0 if all assertions pass, non-zero otherwise. CI-friendly.

**Parallelism:** `--parallel` runs assistants concurrently within each task (each in its own temp directory). Tasks stay sequential.

## Project Structure

```
agent-eval/
  pyproject.toml
  src/
    agent_eval/
      __init__.py
      cli.py                     # typer CLI entrypoint
      config.py                  # YAML config loading & validation
      runner.py                  # orchestrates: load → run → evaluate → report
      adapters/
        __init__.py
        base.py                  # BaseAdapter + AdapterResult
        claude_code.py
        codex.py
        mistral_vibe.py
      assertions/
        __init__.py
        base.py                  # AssertionResult + registry
        deterministic.py         # file_exists, file_contains, command_succeeds
        similarity.py            # bleu, rouge, bertscore, cosine_similarity
      reporting/
        __init__.py
        html.py                  # Jinja2 → single HTML file
        templates/
          report.html.j2
      metrics.py                 # baseline metric collection
  tests/
    test_config.py
    test_assertions.py
    test_adapters.py
    test_reporting.py
  examples/
    terraform-module-eval.yaml
    simple-codegen-eval.yaml
```

## Dependencies

Managed with `uv`.

**Core:**
- `typer` — CLI framework
- `pyyaml` — config parsing
- `jinja2` — HTML report templating
- `pydantic` — config validation and data models

**Optional (similarity metrics):**
- `evaluate` — HuggingFace metrics (BLEU, ROUGE, BERTScore)
- `sentence-transformers` — cosine similarity embeddings
- `bert-score`

```toml
[project.optional-dependencies]
similarity = ["evaluate", "sentence-transformers", "bert-score"]
```

Install: `uv pip install agent-eval[similarity]`

## Future Considerations (not in v1)

- **LLM-as-judge** — Optional qualitative scoring pass after assertions
- **Historical tracking** — Compare runs over time, regression detection
- **Live dashboard** — Flask/FastAPI server for browsing historical runs
- **Custom assertion plugins** — Register via entry points
