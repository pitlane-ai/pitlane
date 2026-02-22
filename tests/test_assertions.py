"""Tests for the deterministic assertion system."""

import importlib.util
import logging

import pytest

from pitlane.assertions.base import AssertionResult
from pitlane.assertions.deterministic import (
    check_command_fails,
    check_command_succeeds,
    check_file_contains,
    check_file_exists,
    evaluate_assertion,
)

# Create a logger for tests that call assertion functions directly
_test_logger = logging.getLogger(__name__)


# --- check_file_exists ---


def test_file_exists_pass(tmp_path):
    (tmp_path / "main.tf").write_text("resource {}")
    result = check_file_exists(tmp_path, "main.tf", _test_logger)
    assert isinstance(result, AssertionResult)
    assert result.passed is True
    assert "main.tf" in result.name


def test_file_exists_fail(tmp_path):
    result = check_file_exists(tmp_path, "missing.tf", _test_logger)
    assert result.passed is False


# --- check_file_contains ---


def test_file_contains_pass(tmp_path):
    (tmp_path / "main.tf").write_text('resource "aws_s3_bucket" "b" {}')
    result = check_file_contains(tmp_path, "main.tf", r"aws_s3_bucket", _test_logger)
    assert result.passed is True


def test_file_contains_fail(tmp_path):
    (tmp_path / "main.tf").write_text("resource {}")
    result = check_file_contains(tmp_path, "main.tf", r"aws_s3_bucket", _test_logger)
    assert result.passed is False


def test_file_contains_missing_file(tmp_path):
    result = check_file_contains(tmp_path, "nope.tf", r"anything", _test_logger)
    assert result.passed is False
    assert (
        "not found" in result.message.lower()
        or "does not exist" in result.message.lower()
    )


# --- check_command_succeeds ---


def test_command_succeeds_pass(tmp_path):
    result = check_command_succeeds(tmp_path, "echo hello", _test_logger)
    assert result.passed is True


def test_command_succeeds_fail(tmp_path):
    result = check_command_succeeds(tmp_path, "false", _test_logger)
    assert result.passed is False


# --- check_command_fails ---


def test_command_fails_pass(tmp_path):
    result = check_command_fails(tmp_path, "false", _test_logger)
    assert result.passed is True


def test_command_fails_fail(tmp_path):
    result = check_command_fails(tmp_path, "true", _test_logger)
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
    r = check_file_exists(tmp_path, "f.txt", _test_logger)
    assert r.score == 1.0

    r2 = check_file_exists(tmp_path, "missing.txt", _test_logger)
    assert r2.score == 0.0


def test_file_contains_sets_score(tmp_path):
    (tmp_path / "f.txt").write_text("hello world")
    r = check_file_contains(tmp_path, "f.txt", "hello", _test_logger)
    assert r.score == 1.0

    r2 = check_file_contains(tmp_path, "f.txt", "missing", _test_logger)
    assert r2.score == 0.0


def test_command_succeeds_sets_score(tmp_path):
    r = check_command_succeeds(tmp_path, "true", _test_logger)
    assert r.score == 1.0

    r2 = check_command_succeeds(tmp_path, "false", _test_logger)
    assert r2.score == 0.0


def test_command_fails_sets_score(tmp_path):
    r = check_command_fails(tmp_path, "false", _test_logger)
    assert r.score == 1.0

    r2 = check_command_fails(tmp_path, "true", _test_logger)
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


def test_similarity_score_normalized_against_min_score(mocker, tmp_path):
    """Similarity scores should be normalized so meeting min_score = 1.0."""
    from pitlane.assertions.similarity import evaluate_similarity_assertion

    (tmp_path / "a.txt").write_text("actual text")
    (tmp_path / "b.txt").write_text("expected text")

    # Mock ROUGE to return a raw score of 0.42 with min_score 0.3
    # Normalized: min(0.42 / 0.3, 1.0) = 1.0 (capped)
    mocker.patch("pitlane.assertions.similarity._score_rouge", return_value=0.42)
    r = evaluate_similarity_assertion(
        tmp_path,
        "rouge",
        {
            "actual": "a.txt",
            "expected": "b.txt",
            "metric": "rougeL",
            "min_score": 0.3,
        },
        logger=_test_logger,
    )
    assert r.passed is True
    assert r.score == 1.0  # 0.42/0.3 > 1.0, capped at 1.0

    # Mock ROUGE to return a raw score of 0.15 with min_score 0.3
    # Normalized: min(0.15 / 0.3, 1.0) = 0.5
    mocker.patch("pitlane.assertions.similarity._score_rouge", return_value=0.15)
    r = evaluate_similarity_assertion(
        tmp_path,
        "rouge",
        {
            "actual": "a.txt",
            "expected": "b.txt",
            "metric": "rougeL",
            "min_score": 0.3,
        },
        logger=_test_logger,
    )
    assert r.passed is False
    assert r.score == pytest.approx(0.5)  # 0.15/0.3 = 0.5


def test_similarity_score_raw_when_no_min_score(mocker, tmp_path):
    """Without min_score, similarity score should be the raw metric value."""
    from pitlane.assertions.similarity import evaluate_similarity_assertion

    (tmp_path / "a.txt").write_text("actual text")
    (tmp_path / "b.txt").write_text("expected text")

    mocker.patch("pitlane.assertions.similarity._score_rouge", return_value=0.42)
    r = evaluate_similarity_assertion(
        tmp_path,
        "rouge",
        {"actual": "a.txt", "expected": "b.txt", "metric": "rougeL"},
        logger=_test_logger,
    )
    assert r.passed is True  # no min_score → always passes
    assert r.score == pytest.approx(0.42)  # raw score, not normalized


# --- check_custom_script ---


def test_custom_script_simple_string(tmp_path):
    """Test simple custom script with string format."""
    script = tmp_path / "test_script.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    script.chmod(0o755)
    result = evaluate_assertion(tmp_path, {"custom_script": "./test_script.sh"})
    assert result.passed is True
    assert result.score == 1.0
    assert "exit code 0" in result.message


def test_custom_script_with_interpreter(tmp_path):
    """Test custom script with interpreter."""
    script = tmp_path / "test.py"
    script.write_text("import sys; sys.exit(0)")

    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python3",
                "script": "./test.py",
            }
        },
    )
    assert result.passed is True
    assert result.score == 1.0


def test_custom_script_with_interpreter_args(tmp_path):
    """Test custom script with interpreter and interpreter args."""
    script = tmp_path / "test.py"
    script.write_text("import sys; print('hello'); sys.exit(0)")

    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python3",
                "interpreter_args": ["-u"],
                "script": "./test.py",
            }
        },
    )
    assert result.passed is True
    assert result.score == 1.0


def test_custom_script_with_script_args(tmp_path):
    """Test custom script with script arguments."""
    script = tmp_path / "test.py"
    script.write_text("""
import sys
if '--strict' in sys.argv and '--format=json' in sys.argv:
    sys.exit(0)
else:
    sys.exit(1)
""")

    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python3",
                "script": "./test.py",
                "script_args": ["--strict", "--format=json"],
            }
        },
    )
    assert result.passed is True
    assert result.score == 1.0


def test_custom_script_all_options(tmp_path):
    """Test custom script with all options."""
    script = tmp_path / "test.py"
    script.write_text("""
import sys
if len(sys.argv) == 3 and sys.argv[1] == '--arg1' and sys.argv[2] == '--arg2':
    sys.exit(0)
else:
    sys.exit(1)
""")

    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python3",
                "interpreter_args": ["-u"],
                "script": "./test.py",
                "script_args": ["--arg1", "--arg2"],
                "timeout": 30,
                "expected_exit_code": 0,
            }
        },
    )
    assert result.passed is True
    assert result.score == 1.0


def test_custom_script_expected_exit_code(tmp_path):
    """Test custom script with non-zero expected exit code."""
    script = tmp_path / "test.sh"
    script.write_text("#!/bin/bash\nexit 42\n")
    script.chmod(0o755)

    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "script": "./test.sh",
                "expected_exit_code": 42,
            }
        },
    )
    assert result.passed is True
    assert result.score == 1.0
    assert "exit code 42" in result.message


def test_custom_script_timeout(tmp_path):
    """Test custom script that times out."""
    script = tmp_path / "test.sh"
    script.write_text("#!/bin/bash\nsleep 10\n")
    script.chmod(0o755)

    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "script": "./test.sh",
                "timeout": 1,
            }
        },
    )
    assert result.passed is False
    assert result.score == 0.0
    assert "timed out" in result.message


def test_custom_script_not_found(tmp_path):
    """Test custom script that doesn't exist."""
    result = evaluate_assertion(tmp_path, {"custom_script": "nonexistent.sh"})
    assert result.passed is False
    assert result.score == 0.0
    assert (
        "not found" in result.message.lower()
        or "no such file" in result.message.lower()
    )


def test_assertions_log_execution(tmp_path, caplog):
    """Verify assertions log execution details."""
    import logging

    logger = logging.getLogger("test_assertion_logger")
    logger.setLevel(logging.DEBUG)

    # Test file_exists logging
    (tmp_path / "test.txt").write_text("content")
    with caplog.at_level(logging.INFO, logger="test_assertion_logger"):
        result = evaluate_assertion(
            tmp_path, {"file_exists": "test.txt"}, logger=logger
        )
        assert result.passed is True

    assert any("Checking file_exists" in record.message for record in caplog.records)

    caplog.clear()

    # Test custom_script logging
    script = tmp_path / "test.sh"
    script.write_text("#!/bin/bash\necho 'hello'\nexit 0\n")
    script.chmod(0o755)

    with caplog.at_level(logging.INFO, logger="test_assertion_logger"):
        result = evaluate_assertion(
            tmp_path, {"custom_script": "./test.sh"}, logger=logger
        )
        assert result.passed is True

    assert any("Running custom_script" in record.message for record in caplog.records)
    assert any("exited with code 0" in record.message for record in caplog.records)
