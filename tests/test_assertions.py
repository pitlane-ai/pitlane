"""Tests for the deterministic assertion system."""

import importlib.util

import pytest

from agent_eval.assertions.base import AssertionResult
from agent_eval.assertions.deterministic import (
    check_command_fails,
    check_command_succeeds,
    check_file_contains,
    check_file_exists,
    evaluate_assertion,
)


# --- check_file_exists ---


def test_file_exists_pass(tmp_path):
    (tmp_path / "main.tf").write_text("resource {}")
    result = check_file_exists(tmp_path, "main.tf")
    assert isinstance(result, AssertionResult)
    assert result.passed is True
    assert "main.tf" in result.name


def test_file_exists_fail(tmp_path):
    result = check_file_exists(tmp_path, "missing.tf")
    assert result.passed is False


# --- check_file_contains ---


def test_file_contains_pass(tmp_path):
    (tmp_path / "main.tf").write_text('resource "aws_s3_bucket" "b" {}')
    result = check_file_contains(tmp_path, "main.tf", r"aws_s3_bucket")
    assert result.passed is True


def test_file_contains_fail(tmp_path):
    (tmp_path / "main.tf").write_text("resource {}")
    result = check_file_contains(tmp_path, "main.tf", r"aws_s3_bucket")
    assert result.passed is False


def test_file_contains_missing_file(tmp_path):
    result = check_file_contains(tmp_path, "nope.tf", r"anything")
    assert result.passed is False
    assert "not found" in result.message.lower() or "does not exist" in result.message.lower()


# --- check_command_succeeds ---


def test_command_succeeds_pass(tmp_path):
    result = check_command_succeeds(tmp_path, "echo hello")
    assert result.passed is True


def test_command_succeeds_fail(tmp_path):
    result = check_command_succeeds(tmp_path, "false")
    assert result.passed is False


# --- check_command_fails ---


def test_command_fails_pass(tmp_path):
    result = check_command_fails(tmp_path, "false")
    assert result.passed is True


def test_command_fails_fail(tmp_path):
    result = check_command_fails(tmp_path, "true")
    assert result.passed is False


# --- evaluate_assertion dispatcher ---


def test_evaluate_assertion_file_exists(tmp_path):
    (tmp_path / "app.py").write_text("print('hi')")
    result = evaluate_assertion(tmp_path, {"file_exists": "app.py"})
    assert result.passed is True


def test_evaluate_assertion_file_contains(tmp_path):
    (tmp_path / "app.py").write_text("import os\nprint('hello')")
    result = evaluate_assertion(
        tmp_path, {"file_contains": {"path": "app.py", "pattern": r"import\s+os"}}
    )
    assert result.passed is True


def test_evaluate_assertion_command_succeeds(tmp_path):
    result = evaluate_assertion(tmp_path, {"command_succeeds": "echo ok"})
    assert result.passed is True


def test_evaluate_assertion_unknown_type():
    with pytest.raises(ValueError, match="[Uu]nknown"):
        evaluate_assertion("/tmp", {"bogus_check": "value"})


def test_evaluate_assertion_similarity_missing_deps_raises():
    deps_present = (
        importlib.util.find_spec("evaluate") is not None
        and importlib.util.find_spec("sentence_transformers") is not None
        and importlib.util.find_spec("bert_score") is not None
    )
    assert deps_present, "Similarity deps must be installed for tests"


def test_evaluate_assertion_similarity_runs(tmp_path):
    (tmp_path / "a.txt").write_text("hello world")
    (tmp_path / "b.txt").write_text("hello world")
    result = evaluate_assertion(
        tmp_path,
        {
            "rouge": {
                "actual": "a.txt",
                "expected": "b.txt",
                "metric": "rougeL",
                "min_score": 0.5,
            }
        },
    )
    assert result.passed is True
    assert 0.0 <= result.score <= 1.0


# --- score and weight fields ---


def test_file_exists_sets_score(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    r = check_file_exists(tmp_path, "f.txt")
    assert r.score == 1.0

    r2 = check_file_exists(tmp_path, "missing.txt")
    assert r2.score == 0.0


def test_file_contains_sets_score(tmp_path):
    (tmp_path / "f.txt").write_text("hello world")
    r = check_file_contains(tmp_path, "f.txt", "hello")
    assert r.score == 1.0

    r2 = check_file_contains(tmp_path, "f.txt", "missing")
    assert r2.score == 0.0


def test_command_succeeds_sets_score(tmp_path):
    r = check_command_succeeds(tmp_path, "true")
    assert r.score == 1.0

    r2 = check_command_succeeds(tmp_path, "false")
    assert r2.score == 0.0


def test_command_fails_sets_score(tmp_path):
    r = check_command_fails(tmp_path, "false")
    assert r.score == 1.0

    r2 = check_command_fails(tmp_path, "true")
    assert r2.score == 0.0


def test_evaluate_assertion_extracts_weight(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    r = evaluate_assertion(tmp_path, {"file_exists": "f.txt", "weight": 3.0})
    assert r.weight == 3.0
    assert r.score == 1.0


def test_evaluate_assertion_default_weight(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    r = evaluate_assertion(tmp_path, {"file_exists": "f.txt"})
    assert r.weight == 1.0


def test_similarity_score_normalized_against_min_score(tmp_path):
    """Similarity scores should be normalized so meeting min_score = 1.0."""
    from agent_eval.assertions.similarity import evaluate_similarity_assertion
    from unittest.mock import patch

    (tmp_path / "a.txt").write_text("actual text")
    (tmp_path / "b.txt").write_text("expected text")

    # Mock ROUGE to return a raw score of 0.42 with min_score 0.3
    # Normalized: min(0.42 / 0.3, 1.0) = 1.0 (capped)
    with patch("agent_eval.assertions.similarity._score_rouge", return_value=0.42):
        r = evaluate_similarity_assertion(
            tmp_path, "rouge",
            {"actual": "a.txt", "expected": "b.txt", "metric": "rougeL", "min_score": 0.3},
        )
    assert r.passed is True
    assert r.score == 1.0  # 0.42/0.3 > 1.0, capped at 1.0

    # Mock ROUGE to return a raw score of 0.15 with min_score 0.3
    # Normalized: min(0.15 / 0.3, 1.0) = 0.5
    with patch("agent_eval.assertions.similarity._score_rouge", return_value=0.15):
        r = evaluate_similarity_assertion(
            tmp_path, "rouge",
            {"actual": "a.txt", "expected": "b.txt", "metric": "rougeL", "min_score": 0.3},
        )
    assert r.passed is False
    assert r.score == pytest.approx(0.5)  # 0.15/0.3 = 0.5


def test_similarity_score_raw_when_no_min_score(tmp_path):
    """Without min_score, similarity score should be the raw metric value."""
    from agent_eval.assertions.similarity import evaluate_similarity_assertion
    from unittest.mock import patch

    (tmp_path / "a.txt").write_text("actual text")
    (tmp_path / "b.txt").write_text("expected text")

    with patch("agent_eval.assertions.similarity._score_rouge", return_value=0.42):
        r = evaluate_similarity_assertion(
            tmp_path, "rouge",
            {"actual": "a.txt", "expected": "b.txt", "metric": "rougeL"},
        )
    assert r.passed is True  # no min_score → always passes
    assert r.score == pytest.approx(0.42)  # raw score, not normalized
