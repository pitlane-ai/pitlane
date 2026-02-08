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
    skills:
      - terraform-ibm-modules/terraform-ibm-modules-skills  # from GitHub via npx skills
      - ./local-skills/my-custom-skill                       # local path (cp -r)

  codex-baseline:
    adapter: codex
    args:
      model: o3

  codex-with-skills:
    adapter: codex
    args:
      model: o3
    skills:
      - terraform-ibm-modules/terraform-ibm-modules-skills

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

Configuration: all via CLI flags (no config files needed).

```bash
claude -p --output-format stream-json --dangerously-skip-permissions \
  --mcp-config ./mcp.json --model sonnet \
  "Create a Terraform module..."
```

| Feature | How |
|---------|-----|
| MCP | `--mcp-config <file>` (or `--strict-mcp-config` to ignore other configs) |
| Skills | Model-invoked skills work automatically. User `/slash` commands are **not available** in `-p` mode. |
| System prompt | `--append-system-prompt` (appends) or `--system-prompt` (replaces) |
| Settings | `--settings <file>` or `--setting-sources` |
| Output | `stream-json` → NDJSON with full conversation (assistant messages, tool_use blocks, tool results). `json` → summary only (no conversation detail). **Use `stream-json` for full capture.** |
| Token usage | Yes — aggregate + per-model breakdown in result message |
| Cost | Yes — `total_cost_usd` in result message |
| Budget limit | `--max-budget-usd` |
| Turn limit | `--max-turns` |
| Permissions | `--dangerously-skip-permissions` or `--allowedTools` |

**CodexAdapter**

Configuration: requires a **project-local `.codex/config.toml`** in the workspace for MCP servers and custom instructions. The adapter generates this file in the temp workspace before invocation. This avoids touching `~/.codex/` and enables safe parallel execution.

```bash
CODEX_HOME=$(mktemp -d) codex exec --json -a never \
  -s workspace-write -m o3 \
  "Create a Terraform module..."
```

| Feature | How |
|---------|-----|
| MCP | `.codex/config.toml` `[mcp_servers.<name>]` tables in workspace (no CLI flag) |
| Skills | Auto-selected based on task. Configured via `agents/openai.yaml` in workspace. |
| System prompt | `AGENTS.md` in workspace root, or `-c model_instructions_file="path"` |
| Output | `--json` → JSONL stream with all events (`turn.started`, `turn.completed`, `item.*`, etc.) |
| Token usage | Yes — `input_tokens`, `cached_input_tokens`, `output_tokens` in `turn.completed` events |
| Cost | Not directly reported — must compute from token counts |
| Sandbox | `--sandbox workspace-write` (or `danger-full-access`) |
| Approval | `-a never` (or `--yolo` for no sandbox + no approval) |

Known issues:
- JSON output schema has drifted from docs ([Issue #4776](https://github.com/openai/codex/issues/4776)) — parser must be defensive
- Some MCP tools silently dropped if JSON Schema uses unsupported features ([Issue #4176](https://github.com/openai/codex/issues/4176))

**MistralVibeAdapter**

Configuration: requires a **project-local `.vibe/config.toml`** in the workspace for MCP servers, system prompt, and model config. The adapter generates this file in the temp workspace before invocation.

```bash
VIBE_HOME=$(mktemp -d) vibe --prompt "Create a Terraform module..." \
  --output json --max-turns 50
```

| Feature | How |
|---------|-----|
| MCP | `.vibe/config.toml` `[[mcp_servers]]` array in workspace (no CLI flag) |
| Skills | Via `enabled_skills` in `config.toml`. Supports glob/regex patterns. |
| System prompt | `system_prompt_id` in `config.toml` pointing to a `.md` file (no CLI flag) |
| Output | `--output json` (all messages as JSON) or `--output streaming` (NDJSON) |
| Token usage | Yes — `usage` field in result message |
| Cost | Yes — `total_cost_usd` in result message |
| Turn limit | `--max-turns N` |
| Cost limit | `--max-price DOLLARS` |
| Auto-approve | Enabled by default in `--prompt` mode |

Known issues:
- Session resume broken — `session_id` missing from streaming output ([Issue #208](https://github.com/mistralai/mistral-vibe/issues/208))
- `--enabled-tools` in `--prompt` mode **disables all tools not explicitly listed** (stricter than interactive mode)

### Skill Installation

Skills are installed **automatically** by the harness as a setup step before invoking any assistant. The `skills` field in the eval config supports two sources:

```yaml
skills:
  - terraform-ibm-modules/terraform-ibm-modules-skills  # GitHub repo
  - ./local-skills/my-custom-skill                       # local path
```

**Installation process per adapter run:**

1. Create the temp workspace (copy from `workdir`)
2. For each skill in the assistant's `skills` list:
   - **GitHub reference** (e.g. `org/repo`): run `npx skills install <ref> --agent <agent-type> --yes` in the workspace. This places skill files in the agent-specific directory (`.claude/skills/`, `.codex/skills/`, `.vibe/skills/`).
   - **Local path** (starts with `./` or `/`): `cp -r` the skill directory into the workspace's agent-specific skill directory.
3. Run the assistant CLI

**Agent-to-directory mapping for local copies:**

| Adapter | Skill install directory |
|---------|----------------------|
| Claude Code | `<workspace>/.claude/skills/<skill-name>/` |
| Codex | `<workspace>/.codex/skills/<skill-name>/` |
| Vibe | `<workspace>/.vibe/skills/<skill-name>/` |

**Why this matters for the TDD loop:** When iterating on a local skill, you edit the skill files, then re-run `agent-eval run eval.yaml`. The harness copies the latest version into each workspace automatically — no manual install step.

**Pre-flight validation:** Before running, the harness verifies:
- GitHub skills: `npx skills` is available (`which npx`)
- Local skills: path exists and contains a `SKILL.md` file
- Failures are reported immediately, before any assistant is invoked

### Parallel Execution & Workspace Isolation

Each adapter run gets its own **isolated temp directory** (copied from the task's `workdir`). This is critical for three reasons:

1. **No workspace conflicts** — assistants don't overwrite each other's files
2. **Config file isolation** — Codex and Vibe adapters write project-local config files (`.codex/config.toml`, `.vibe/config.toml`) inside the temp workspace. These take priority over home directory configs.
3. **Home directory safety** — As extra insurance, adapters set `CODEX_HOME` / `VIBE_HOME` environment variables to temp directories in the subprocess env, ensuring zero bleed to the user's actual home config even if something reads global config.

| CLI | Config method | Home dir touched? | Parallel safe? |
|-----|--------------|-------------------|----------------|
| Claude Code | CLI flags only | No | Yes |
| Codex | `.codex/config.toml` in workspace + `CODEX_HOME` env | No | Yes |
| Vibe | `.vibe/config.toml` in workspace + `VIBE_HOME` env | No | Yes |

### Conversation Normalization

Each CLI outputs conversation data in a different format. Adapters normalize into a common structure:

```python
# Normalized conversation entry
{
    "role": "assistant" | "user" | "tool",
    "content": str,
    "tool_use": {              # optional, present for tool calls
        "name": str,
        "input": dict,
        "output": str,
    },
    "timestamp": float,        # relative to run start
}
```

| CLI | Source format | Parsing approach |
|-----|-------------|-----------------|
| Claude Code | `stream-json` NDJSON — Anthropic API message objects with `text` and `tool_use` content blocks | Direct mapping |
| Codex | JSONL events — `item.*` events with `agent_message`, command executions, MCP tool calls | Event-type dispatch, defensive parsing due to schema drift |
| Vibe | `--output json` — messages array with `role`, `content` fields | Direct mapping, tool call structure TBD |

### Adding New Adapters

Adding a new assistant means writing one class (~50-100 lines) that implements `run()`. The adapter handles:
- CLI invocation flags
- Config file generation (if needed)
- Output format parsing into `AdapterResult`
- Conversation normalization

Everything upstream (config, workspace setup) and downstream (assertions, metrics, reporting) is generic.

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

## Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Codex JSON schema drift | Parser breaks on new Codex versions | Defensive parsing, version detection, integration tests against real CLI |
| MCP tools silently dropped (Codex) | Eval runs without expected tools, gives misleading results | Pre-flight check: verify MCP tools loaded via output stream, warn if expected tools missing |
| Vibe session resume broken | Cannot resume failed runs for Vibe | Not needed for eval — each run is independent |
| CLI version changes | Adapters break on new releases | Pin tested CLI versions in docs, adapter version detection |
| Large model downloads (BERTScore) | First similarity assertion run is slow | Document in README, optional extra install, cache models |

## Future Considerations (not in v1)

- **LLM-as-judge** — Optional qualitative scoring pass after assertions
- **Historical tracking** — Compare runs over time, regression detection
- **Live dashboard** — Flask/FastAPI server for browsing historical runs
- **Custom assertion plugins** — Register via entry points
- **Multi-turn eval** — Feed follow-up prompts based on assistant output (requires `stream-json` input for Claude, session resume for others)
