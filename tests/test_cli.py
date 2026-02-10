import pytest
from pathlib import Path
from typer.testing import CliRunner
from agent_eval.cli import app

runner = CliRunner()


def test_init_creates_example_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "agent-eval" / "eval.yaml").exists()
    assert (tmp_path / "agent-eval" / "fixtures" / "empty" / ".gitkeep").exists()


def test_init_with_custom_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--dir", "my-custom-dir"])
    assert result.exit_code == 0
    assert (tmp_path / "my-custom-dir" / "eval.yaml").exists()
    assert (tmp_path / "my-custom-dir" / "fixtures" / "empty" / ".gitkeep").exists()


def test_run_missing_config():
    result = runner.invoke(app, ["run", "nonexistent.yaml"])
    assert result.exit_code != 0


def test_report_missing_dir():
    result = runner.invoke(app, ["report", "/tmp/nonexistent-run-dir"])
    assert result.exit_code != 0


def test_schema_command_writes_files(tmp_path):
    out = tmp_path / "schema.json"
    doc = tmp_path / "schema.md"
    result = runner.invoke(
        app, ["schema", "--out", str(out), "--doc", str(doc)]
    )
    assert result.exit_code == 0
    assert out.exists()
    assert doc.exists()
