import pytest
from pathlib import Path
from typer.testing import CliRunner
from agent_eval.cli import app

runner = CliRunner()


def test_init_creates_example_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "eval.yaml").exists()


def test_run_missing_config():
    result = runner.invoke(app, ["run", "nonexistent.yaml"])
    assert result.exit_code != 0


def test_report_missing_dir():
    result = runner.invoke(app, ["report", "/tmp/nonexistent-run-dir"])
    assert result.exit_code != 0
