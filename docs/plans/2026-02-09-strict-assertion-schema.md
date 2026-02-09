# Strict Assertion Schema + Similarity Assertions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make eval YAML assertions fully defined in Pydantic (strict schema generation) and implement similarity assertions (bleu/rouge/bertscore/cosine_similarity).

**Architecture:** Introduce explicit Pydantic models for each assertion type and use a Union for validation. Add a new similarity evaluator module that reads file contents and computes metrics, with optional dependency checks and clear error messages. Update tests to enforce strict validation and similarity behavior.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, optional deps: evaluate, sentence-transformers, bert-score. Use `uv` for installs.

---

### Task 1: Update Pydantic assertion models to be strict and schema-complete

**Files:**
- Modify: `src/agent_eval/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Add tests that validate known assertion shapes are accepted and unknown shapes are rejected.

```python
# tests/test_config.py

def test_assertion_validation_accepts_known(tmp_yaml):
    path = tmp_yaml("""
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - file_exists: "x.py"
              - file_contains: { path: "x.py", pattern: "def" }
              - command_succeeds: "echo ok"
              - command_fails: "false"
              - bleu: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
              - rouge: { actual: "a.txt", expected: "b.txt", metric: "rougeL", min_score: 0.1 }
              - bertscore: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
              - cosine_similarity: { actual: "a.txt", expected: "b.txt", min_score: 0.1 }
    """)
    load_config(path)


def test_assertion_validation_rejects_unknown(tmp_yaml):
    path = tmp_yaml("""
        assistants:
          a:
            adapter: claude-code
        tasks:
          - name: t
            prompt: p
            workdir: /tmp
            assertions:
              - unknown_type: { x: 1 }
    """)
    with pytest.raises(Exception):
        load_config(path)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_assertion_validation_accepts_known -v`
Expected: FAIL (assertion validation not strict yet)

Run: `pytest tests/test_config.py::test_assertion_validation_rejects_unknown -v`
Expected: FAIL (unknown types currently allowed)

**Step 3: Write minimal implementation**

Define explicit Pydantic models for assertions and replace `assertions: list[dict[str, Any]]` with a strict Union type. Use `extra="forbid"` to reject unknown keys and use `one-of`-style assertion models (each with a single known key).

```python
# src/agent_eval/config.py
from pydantic import BaseModel, ConfigDict
from typing import Union

class FileExistsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_exists: str

class FileContainsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    pattern: str

class FileContainsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_contains: FileContainsSpec

class CommandSucceedsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_succeeds: str

class CommandFailsAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_fails: str

class SimilaritySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual: str
    expected: str
    metric: str | None = None
    min_score: float | None = None

class BleuAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bleu: SimilaritySpec

class RougeAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rouge: SimilaritySpec

class BERTScoreAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bertscore: SimilaritySpec

class CosineSimilarityAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cosine_similarity: SimilaritySpec

Assertion = Union[
    FileExistsAssertion,
    FileContainsAssertion,
    CommandSucceedsAssertion,
    CommandFailsAssertion,
    BleuAssertion,
    RougeAssertion,
    BERTScoreAssertion,
    CosineSimilarityAssertion,
]

class TaskConfig(BaseModel):
    ...
    assertions: list[Assertion]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_assertion_validation_accepts_known -v`
Expected: PASS

Run: `pytest tests/test_config.py::test_assertion_validation_rejects_unknown -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent_eval/config.py tests/test_config.py
git commit -m "feat: strict assertion schema in config"
```

---

### Task 2: Implement similarity assertions evaluation

**Files:**
- Create: `src/agent_eval/assertions/similarity.py`
- Modify: `src/agent_eval/assertions/deterministic.py`
- Test: `tests/test_assertions.py`

**Step 1: Write the failing test**

Add tests that verify similarity assertions are dispatched and either compute a score (if deps present) or raise a helpful error (if deps missing).

```python
# tests/test_assertions.py
import importlib.util


def _similarity_deps_present() -> bool:
    return (
        importlib.util.find_spec("evaluate") is not None
        and importlib.util.find_spec("sentence_transformers") is not None
        and importlib.util.find_spec("bert_score") is not None
    )


def test_evaluate_assertion_similarity_missing_deps_raises():
    if _similarity_deps_present():
        pytest.skip("similarity deps installed")
    for kind in ("bleu", "rouge", "bertscore", "cosine_similarity"):
        with pytest.raises(ValueError, match="agent-eval\\[similarity\\]"):
            evaluate_assertion("/tmp", {kind: {"actual": "a", "expected": "b"}})


def test_evaluate_assertion_similarity_runs(tmp_path):
    if not _similarity_deps_present():
        pytest.skip("similarity deps missing")
    (tmp_path / "a.txt").write_text("hello world")
    (tmp_path / "b.txt").write_text("hello world")
    result = evaluate_assertion(tmp_path, {
        "rouge": {"actual": "a.txt", "expected": "b.txt", "metric": "rougeL", "min_score": 0.5}
    })
    assert result.passed is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_assertions.py::test_evaluate_assertion_similarity_missing_deps_raises -v`
Expected: FAIL (current code raises different error or message)

Run: `pytest tests/test_assertions.py::test_evaluate_assertion_similarity_runs -v`
Expected: FAIL (no similarity evaluator)

**Step 3: Write minimal implementation**

Implement `evaluate_similarity_assertion()` to load the correct metric, read file contents, compute score, and compare to `min_score`. If optional dependencies are missing, raise `ValueError` with install guidance.

```python
# src/agent_eval/assertions/similarity.py
from pathlib import Path
from agent_eval.assertions.base import AssertionResult


def _require_similarity_deps():
    try:
        import evaluate  # noqa: F401
        import sentence_transformers  # noqa: F401
        import bert_score  # noqa: F401
    except Exception as exc:
        raise ValueError(
            "Similarity assertions require optional deps. Install with: uv pip install '.[similarity]'"
        ) from exc


def evaluate_similarity_assertion(workdir: str | Path, kind: str, spec: dict) -> AssertionResult:
    _require_similarity_deps()
    # ... compute score, compare to min_score, return AssertionResult
```

Wire this into `evaluate_assertion()` in `src/agent_eval/assertions/deterministic.py` so similarity types are dispatched instead of raising.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_assertions.py::test_evaluate_assertion_similarity_missing_deps_raises -v`
Expected: PASS (skip if deps installed)

Run: `pytest tests/test_assertions.py::test_evaluate_assertion_similarity_runs -v`
Expected: PASS (skip if deps missing)

**Step 5: Commit**

```bash
git add src/agent_eval/assertions/deterministic.py src/agent_eval/assertions/similarity.py tests/test_assertions.py
git commit -m "feat: implement similarity assertions"
```

---

### Task 3: Add schema/doc generation command from Pydantic

**Files:**
- Modify: `src/agent_eval/cli.py`
- Create: `src/agent_eval/schema.py`
- Create: `schemas/agent-eval.schema.json`
- Create: `docs/schema.md`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add a CLI test for a new `agent-eval schema` command that writes JSON Schema and docs.

```python
# tests/test_cli.py

def test_schema_command_writes_files(tmp_path):
    result = runner.invoke(app, ["schema", "--out", str(tmp_path / "schema.json"), "--doc", str(tmp_path / "schema.md")])
    assert result.exit_code == 0
    assert (tmp_path / "schema.json").exists()
    assert (tmp_path / "schema.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_schema_command_writes_files -v`
Expected: FAIL (command not implemented)

**Step 3: Write minimal implementation**

Create `src/agent_eval/schema.py` to:
- call `EvalConfig.model_json_schema()`
- write JSON to `schemas/agent-eval.schema.json` (default)
- write a short Markdown doc describing top-level keys and assertion variants (default)

Add a new Typer command in `src/agent_eval/cli.py`:
- `agent-eval schema [--out path] [--doc path]`
- defaults: `schemas/agent-eval.schema.json` and `docs/schema.md`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_schema_command_writes_files -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent_eval/cli.py src/agent_eval/schema.py schemas/agent-eval.schema.json docs/schema.md tests/test_cli.py
git commit -m "feat: add schema/doc generation command"
```

---

### Task 4: Update config tests and example fixtures to match strict schema

**Files:**
- Modify: `tests/test_config.py`
- Verify: `examples/simple-codegen-eval.yaml`
- Verify: `examples/terraform-module-eval.yaml`

**Step 1: Write the failing test**

Ensure `tests/test_config.py` assertions use the new schema (they currently use legacy `type`/`value`).

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_load_minimal_config -v`
Expected: FAIL (legacy assertion format)

**Step 3: Write minimal implementation**

Update tests to use new assertion shapes, e.g.:

```python
assertions:
  - file_exists: "hello.py"
```

Confirm example YAML already uses the correct formats; adjust if necessary.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_load_minimal_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_config.py examples/simple-codegen-eval.yaml examples/terraform-module-eval.yaml
git commit -m "test: update config fixtures for strict schema"
```

---

### Task 5: Full test pass

**Files:**
- Test: `tests/`

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --short
```

If changes remain:

```bash
git add -A
git commit -m "test: full pass"
```
