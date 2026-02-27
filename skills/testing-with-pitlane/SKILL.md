---
name: testing-with-pitlane
description: >
  Design and create pitlane eval benchmarks that measure whether an AI coding
  skill or MCP server actually improves assistant performance. Use when the user
  wants to test a skill, evaluate an MCP server, create a pitlane eval YAML,
  benchmark an AI assistant, or compare baseline vs challenger configurations.
  Covers eval design, assertion strategy, fixture setup, and result interpretation.
category: testing
tags:
  - pitlane
  - evaluation
  - benchmarking
  - skills
  - mcp
---

# Testing skills and MCP servers with pitlane

Help users design pitlane eval benchmarks that answer one question: "Does my skill or MCP server actually make the assistant better?"

## What pitlane is

Pitlane is an eval harness for AI coding assistants. You define coding tasks in a YAML file, run them against a baseline assistant (without your skill) and a challenger (with your skill), and pitlane tells you which one did better. It tracks pass rates, quality scores, time, tokens, and cost.

Think of it as A/B testing for skills and MCP servers.

## Setup

Install pitlane if the user doesn't have it yet:

```bash
# installs pitlane cli
uv tool install pitlane --from git+https://github.com/vburckhardt/pitlane.git
pitlane pitlane_command
# or (no intall with uvx)
uvx --from git+https://github.com/vburckhardt/pitlane.git pitlane pitlane_command
```

The user also needs at least one AI coding assistant CLI installed. Pitlane supports four assistants:

| Type | CLI | Cheap model for iteration |
|------|-----|--------------------------|
| `claude-code` | `claude` | `haiku` |
| `mistral-vibe` | `vibe` | `devstral-small` |
| `opencode` | `opencode` | `minimax-m2.5-free` (free) |
| `bob` | `bob` | N/A |

Scaffold a new eval project with `pitlane init`. This creates an `eval.yaml` and a `fixtures/empty/` directory to get started.

## How an eval YAML works

An eval file has two sections: `assistants` (who runs the tasks) and `tasks` (what they do and how to check the results).

`pitlane schema generate` generates the schema for the eval file. Use it to discover advanced capabilities.

```yaml
assistants:
  baseline:
    type: claude-code       # or mistral-vibe, opencode
    args:
      model: haiku
  with-skill:
    type: claude-code
    args:
      model: haiku
    skills:
      - source: org/repo       # github org/repo for the skill
        skill: skill-name      # optional, only if repo has multiple skills

tasks:
  - name: my-task
    prompt: "What the assistant should do"
    workdir: ./fixtures/my-task   # copied fresh for each run
    timeout: 300
    assertions:
      - file_exists: "output.py"
      - command_succeeds: "python output.py"
      - file_contains: { path: "output.py", pattern: "def main" }
```

For MCP servers instead of skills, pass the config through assistant args:

```yaml
# Claude Code
with-mcp:
  type: claude-code
  args:
    model: haiku
    mcp_config: ./mcp-config.json

# Mistral Vibe
with-mcp:
  type: mistral-vibe
  args:
    model: devstral-small
    mcp_servers:
      - name: my-server
        url: http://localhost:3000
```

### Assertions

Deterministic (prefer these):

- `file_exists: "path"` -- does the file exist?
- `file_contains: { path: "file", pattern: "regex" }` -- does it match a regex?
- `command_succeeds: "cmd"` -- does the command exit 0?
- `command_fails: "cmd"` -- does it exit non-zero?
- `custom_script: "python validate.py"` -- run a validation script (also supports advanced form with `script`, `args`, `timeout`, `expected_exit_code`)

Similarity (requires `pip install pitlane[similarity]`):

- `rouge: { actual: "file", expected: "./refs/golden.md", metric: "rougeL", min_score: 0.35 }` -- topic coverage, fast, good for docs
- `bleu: { actual: "file", expected: "./refs/golden.md", min_score: 0.15 }` -- phrase matching, fast, good for docs but bad for code
- `bertscore: { actual: "file", expected: "./refs/golden.md", min_score: 0.75 }` -- semantic similarity, slow, works for docs and code
- `cosine_similarity: { actual: "file", expected: "./refs/golden.tf", min_score: 0.7 }` -- overall meaning, slow, best for code and configs

Any assertion can take a `weight` (default 1.0) to make it count more in the `weighted_score`.

### Running

```bash
pitlane run eval.yaml                                    # run everything
pitlane run eval.yaml --task my-task                     # one task only
pitlane run eval.yaml --only-assistants baseline          # run only these assistants (comma-separated)
pitlane run eval.yaml --skip-assistants baseline          # skip these assistants (comma-separated)
pitlane run eval.yaml --parallel 4                       # run tasks in parallel
pitlane run eval.yaml --repeat 5                         # repeat for statistical confidence
pitlane run eval.yaml --verbose                          # stream debug output
```

These options can be combined, eg: `pitlane run eval.yaml --task my-task --only-assistants baseline --repeat 5 --parallel 4`

Results go to `runs/<timestamp>/` with `report.html` (side-by-side comparison), `results.json`, and `debug.log`.

## Eval design

This is the hard part. The syntax above is straightforward; designing evals that produce real signal is not.

Before writing any YAML, work through these questions with the user.

### What is the knowledge delta?

The skill or MCP server gives the assistant something it doesn't have by default. The eval has to target that gap directly.

- What can the assistant do WITH the skill that it can't do WITHOUT? Test that.
- What's the smallest task where the skill makes a difference? Start there, not with a complex integration test.
- Would a strong model pass this task anyway? If so, the task measures the model, not the skill.

### Isolate the variable

The only difference between baseline and challenger should be the skill or MCP server. Everything else stays identical: same model, same prompt (word for word), same fixture directory, same timeout.

If the challenger prompt says "use the MCP tool to...", you're testing prompt engineering, not the skill.

### Start cheap, validate expensive

Use a cheaper or weaker model during development. Weaker models amplify the skill's effect because they struggle more without help, which makes the delta easier to see. Switch to a stronger model for final benchmarks to confirm the skill helps capable models too.

## Assertion strategy

### Layer your assertions

Design assertions in rough order of importance:

1. Did the assistant produce the expected files? (`file_exists`)
2. Does the output actually work? (`command_succeeds`, `file_contains`)
3. How close is it to a known-good solution? (similarity metrics, `custom_script`)

Weight them accordingly. A passing test suite (`command_succeeds` at weight 3.0) matters more than a README existing (`file_exists` at weight 1.0).

### Prefer deterministic assertions

Similarity metrics are tempting but noisy. Reach for deterministic assertions first:

- Instead of cosine_similarity on `main.tf`, use `file_contains` to check for specific module sources.
- Instead of rouge on a README, use `file_contains` to check that key sections exist.
- Save similarity for genuinely open-ended outputs like free-form documentation.

When you do use similarity, set `min_score` conservatively. Scores vary between runs. If your threshold is tight, `--repeat 5` will show you the variance.

### Custom scripts for complex validation

When `file_contains` and `command_succeeds` aren't expressive enough, write a custom script. Place it in the fixture directory (it gets copied to the workspace) or reference it with a relative path.

Good candidates: multi-step validation (parse JSON, check field relationships), domain-specific checks (API response format, dependency graphs), or conditional logic (if file A exists, B must contain X).

## NEVER

- NEVER write prompts that hint at the skill's existence. The prompt describes the task, not how to solve it. If your prompt says "use module X from registry Y", you're testing instruction-following, not the skill.
- NEVER test with only one task. A single task can pass or fail for unrelated reasons. Use 3+ tasks at different difficulty levels.
- NEVER skip the baseline. Without one, you can't attribute results to the skill. "It passes" means nothing if it also passes without the skill.
- NEVER use tight similarity thresholds without `--repeat`. A min_score of 0.7 that passes once and fails twice is not a passing assertion. Run at least 3 repeats for similarity-based evals.
- NEVER put golden references in the fixture root. They go in `refs/`, which pitlane excludes from the workspace. If the assistant can see the expected output, the eval is meaningless.
- NEVER cram everything into one mega-task. "Create a full application with auth, database, API, and tests" measures general coding ability, not your skill. Split into focused tasks that isolate what the skill improves.
- NEVER assume `command_succeeds` means the code is correct. `python main.py` exiting 0 says nothing about output correctness. Combine with `file_contains` or pipe output through a validation script.
- NEVER set timeouts too tight during development. Start with 300-600s. Tighten after you know the baseline completion time. A timeout failure tells you nothing about skill quality.

## Fixture design

### Empty vs pre-populated

Use an empty fixture (`fixtures/empty/` with a `.gitkeep`) when your skill helps with greenfield creation like scaffolding or boilerplate. Use a pre-populated fixture when the skill helps with modification or enhancement of existing code. Seed it with realistic starter files.

### The refs/ directory

Golden references live in a `refs/` subdirectory inside each fixture. Pitlane excludes `refs/` when copying the fixture to the workspace, so the assistant never sees them. They're used as targets for similarity assertions (`expected: "./refs/expected-main.tf"`) and as documentation of what "good" looks like for human reviewers.

Write reference files by hand or curate them from known-good outputs. Don't generate them with the same model you're testing.

## Interpreting results

### Metrics that matter

- `assertion_pass_rate` compares baseline vs challenger directly. If both hit 100%, the tasks are too easy. If baseline is already at 80%+, the skill has less room to prove itself.
- `weighted_score` is more nuanced than pass_rate when you're using weights and similarity metrics. Compare the delta between baseline and challenger.
- `cost_usd` and `wall_clock_seconds` track the trade-off. A skill that improves quality at 3x the cost may not be worth it.

### Reading the results

| Signal | What it means |
|--------|---------------|
| Baseline low, challenger high | The skill is working |
| Both high | Tasks are too easy, add harder ones |
| Both low | Tasks may be too hard, or the skill needs work |
| Baseline high, challenger low | The skill is hurting, investigate |
| High variance across `--repeat` runs | Assertions or prompts need tightening |

### The iteration loop

This is TDD applied to skills:

1. Write tasks and assertions the skill should help with. Run the baseline. It should struggle.
2. Run with the skill. If it doesn't improve, the skill needs work, not the eval.
3. Tighten assertions, add edge cases, increase difficulty. Repeat.

If the baseline already passes everything, the eval isn't testing the skill's value. Go back to "what is the knowledge delta?"
