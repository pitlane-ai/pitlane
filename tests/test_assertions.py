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
