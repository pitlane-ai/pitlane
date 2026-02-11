# agent-eval

Build a skill or MCP? Use `agent-eval` to measure if it works and who it helps.
`agent-eval` provides a repeatable harness for evaluating skill/MCP changes across assistants.
It runs your YAML-defined tasks, checks assertions, and produces a report with pass rates plus practical metrics like wall-clock time, token usage, tool calls, cost (when available), and file/line changes.

## Why this exists

`agent-eval` makes it easy to build your own benchmark and run it in a TDD loop (red, green, refactor) against common AI assistants. It focuses on two goals:
- Simplify creating skills/MCP-based tasks so you can iterate quickly on what "good" looks like.
- Compare performance across assistants in a consistent, repeatable way.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended package manager)

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

For faster execution on multi-task benchmarks, use parallel execution:

```bash
agent-eval run examples/simple-codegen-eval.yaml --parallel 4
```

Outputs are written to `runs/` by default (gitignored) and include `results.json`, `meta.yaml`, `debug.log`, and an HTML report.

### Debug Output

Every run creates `debug.log` with command execution details. Add `--verbose` (or `-v`) to also stream output to terminal.

## Config Format

Keep benchmarks as plain YAML so you can diff, review, and iterate quickly.

Top-level keys:
- `assistants`: mapping of assistant names to config.
- `tasks`: list of task definitions.

See the examples:
- `examples/simple-codegen-eval.yaml` — minimal, deterministic assertions only.
- `examples/similarity-codegen-eval.yaml` — extends simple codegen with ROUGE, BLEU, BERTScore, and cosine similarity, with guidance on which metrics suit code vs docs.
- `examples/terraform-module-eval.yaml` — real-world Terraform eval with skills, multiple assistants, and all assertion types.
- `examples/weighted-grading-eval.yaml` — demonstrates weighted assertions and continuous scoring for finer-grained grading.

### Assistants

An assistant entry tells `agent-eval` how to run a model. Each assistant has:
- `adapter`: which runner to use (run `agent-eval run --help` to list available adapters).
- `args`: adapter-specific settings (often the model name).
- `skills`: optional list of skills (based on the specs at [agentskills.io](https://agentskills.io)) or MCP sources to inject for that assistant.

Use multiple assistants to compare baseline vs skill-augmented behavior side by side.

```yaml
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: haiku

  claude-with-skill:
    adapter: claude-code
    args:
      model: haiku
    skills:
      - source: org/repo
        skill: my-skill-name
```

### Tasks

Each task defines the prompt, workspace, and assertions. Minimal shape:
- `name`
- `prompt`
- `workdir` (fixture directory to run in)
- `timeout`
- `assertions` (file checks, command checks, or similarity metrics)

```yaml
tasks:
  - name: hello-world-python
    prompt: "Create a Python script called hello.py that prints 'Hello, World!'"
    workdir: ./fixtures/empty
    timeout: 120
    assertions:
      # Does the file exist?
      - file_exists: "hello.py"
      # Does running it succeed?
      - command_succeeds: "python hello.py"
      # Does the file contain expected content?
      - file_contains: { path: "hello.py", pattern: "Hello, World!" }
```

### Similarity Assertions

When exact text matching isn't practical (generated prose, code with variable formatting), use similarity metrics to compare an output file against a golden reference. All four share the same YAML shape:

```yaml
{ actual: "<output-file>", expected: "<reference-file>", metric: "<variant>", min_score: 0.5 }
```

- `actual` — path to the generated file (relative to the task workdir).
- `expected` — path to the golden reference (relative to the task workdir or the eval YAML directory with `./`).
- `metric` — optional variant (only used by ROUGE and BERTScore, ignored by the others).
- `min_score` — threshold to pass (0.0–1.0). Omit to always pass and just record the score.

#### ROUGE — does the output cover the same topics?

Checks how much of the reference content shows up in the generated text. Think of it as: "did the output mention the same things as the reference?"

```yaml
- rouge: { actual: "README.md", expected: "./refs/golden.md", metric: "rougeL", min_score: 0.35 }
```

`metric` variants: `rouge1` (single words), `rouge2` (word pairs), `rougeL` (longest shared sequence, default). Scores are 0–1.

**Good for:** Documentation, README quality — "did it cover the same topics?"
**Not great for:** Code files where structure and order matter more than word coverage.

#### BLEU — does the output use the same phrases?

Checks how many words and phrases from the generated text also appear in the reference. Think of it as: "does the output use the right terminology?"

```yaml
- bleu: { actual: "README.md", expected: "./refs/golden.md", min_score: 0.2 }
```

No `metric` variants. Scores are 0–1.

**Good for:** Documentation and prose where you expect similar phrasing to the reference.
**Not great for code.** Even functionally identical code scores low because of naming, whitespace, and formatting differences. For code, use `cosine_similarity` or `bertscore` instead. If you need specific tokens in code, `file_contains` is more reliable.

#### BERTScore — does the output mean the same thing?

Uses an AI language model to judge whether two texts express the same meaning, even if they use completely different words. More expensive to run but catches things word-matching misses.

```yaml
- bertscore: { actual: "README.md", expected: "./refs/golden.md", min_score: 0.75 }
```

`metric` variants: `precision`, `recall`, `f1` (default). Scores are 0–1. Hardcoded to English. Loads a model on first use, so it's slower than ROUGE/BLEU.

**Good for:** Documentation that should convey the same ideas regardless of exact wording.
**Not great for:** Large files where speed matters, or when you need specific words to appear (use `file_contains` instead).

#### Cosine Similarity — are these texts about the same thing?

Converts both files into a numerical "fingerprint" of their meaning and measures how close they are. Completely ignores word choice and order — only the overall meaning matters.

```yaml
- cosine_similarity: { actual: "variables.tf", expected: "./refs/expected-vars.tf", min_score: 0.7 }
```

No `metric` variants. Scores are 0–1. Also loads a model on first use (uses `all-MiniLM-L6-v2`).

**Good for:** Checking that variable definitions, output blocks, or configs are semantically similar.
**Not great for:** Cases where specific tokens or wording must appear — use BLEU or `file_contains` instead.

#### Choosing the right metric

| Metric | Question it answers | Speed | Best for |
|---|---|---|---|
| Metric | Question it answers | Speed | Best for |
|---|---|---|---|
| `rouge` | Did it cover the same topics? | Fast | Docs, README coverage |
| `bleu` | Did it use the same phrases? | Fast | Docs with expected phrasing (not code) |
| `bertscore` | Does it mean the same thing? | Slow | Docs or code — meaning preservation |
| `cosine_similarity` | Is it about the same thing? | Slow | Code or configs — semantic similarity |

Start with deterministic assertions (`file_exists`, `command_succeeds`, `file_contains`) and add similarity metrics only where exact matching breaks down. Combine them — e.g. use `file_contains` to verify critical tokens, then `rouge` or `bertscore` to check overall quality.

### Weighted Grading

By default every assertion counts equally toward the pass rate. Add a `weight` field to make some assertions count more than others, and get a `weighted_score` metric that uses continuous scores instead of binary pass/fail.

```yaml
assertions:
  - file_exists: "main.tf"
  - command_succeeds: "terraform validate"
    weight: 3.0            # 3x more important than default
  - rouge: { actual: "README.md", expected: "./refs/golden.md", metric: "rougeL", min_score: 0.3 }
    weight: 2.0
```

**How it works:**

- `weight` defaults to 1.0 when omitted — fully backward compatible.
- Binary assertions (file checks, commands) score 1.0 on pass, 0.0 on fail.
- Similarity assertions with `min_score` are normalized against the threshold: meeting the threshold = 1.0, half the threshold = 0.5. This avoids raw metric values (e.g. BLEU 0.3) dragging down the grade even when they pass.
- Similarity assertions without `min_score` use the raw metric value.
- The `weighted_score` metric is: `sum(weight * score) / sum(weight) * 100`.

Both `assertion_pass_rate` (unweighted binary) and `weighted_score` appear in `results.json` and the HTML report. Use `assertion_pass_rate` for a quick pass/fail overview and `weighted_score` when you want to express that some assertions matter more or want credit for partial similarity.

See `examples/weighted-grading-eval.yaml` for a working example.

### Task Design Tips

- Prefer deterministic assertions (file checks and commands) to keep runs stable.
- Use similarity metrics when exact text is not required.
- Keep workdirs small and focused so red/green loops stay fast.
- Set similarity thresholds conservatively at first, then tighten as you iterate.

### TDD Loop

The intended workflow is to treat your eval like a test suite:
1. Red: add or tighten assertions that capture the behavior you want.
2. Green: update skills or MCP sources until the assertions pass.
3. Refactor: clean prompts, tasks, and fixtures without changing outcomes.

## VS Code and VS Code Clones

Install it automatically (safe by default):

```bash
uv run agent-eval schema install
```

This is intended for editors that use `.vscode/settings.json` (VS Code, Cursor, Kiro, Bob).
It previews changes, asks for confirmation, and creates a backup by default.

Map the schema in `.vscode/settings.json`:

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

Per-file schema (optional):

```yaml
# yaml-language-server: $schema=./agent-eval/schemas/agent-eval.schema.json
```

## Schema Generation (Other Editors)

If your editor does not use `.vscode/settings.json`, generate the schema/docs directly:

```bash
uv run agent-eval schema generate
```

This writes:
- `agent-eval/schemas/agent-eval.schema.json`
- `agent-eval/docs/schema.md`

Use `--dir .` to generate into the current directory instead.
