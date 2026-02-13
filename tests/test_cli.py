import json
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


def test_schema_generate_command_writes_files(tmp_path):
    out = tmp_path / "schema.json"
    doc = tmp_path / "schema.md"
    result = runner.invoke(
        app, ["schema", "generate", "--out", str(out), "--doc", str(doc)]
    )
    assert result.exit_code == 0
    assert out.exists()
    assert doc.exists()


def test_schema_generate_defaults_to_init_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["schema", "generate"])
    assert result.exit_code == 0
    assert (tmp_path / "agent-eval" / "schemas" / "agent-eval.schema.json").exists()
    assert (tmp_path / "agent-eval" / "docs" / "schema.md").exists()


def test_schema_install_requires_yes_in_non_interactive_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["schema", "install"])
    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert (tmp_path / "agent-eval" / "schemas" / "agent-eval.schema.json").exists()
    assert (tmp_path / "agent-eval" / "docs" / "schema.md").exists()
    assert not (tmp_path / ".vscode" / "settings.json").exists()


def test_schema_install_writes_settings_and_preserves_unrelated_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"editor.tabSize": 2, "yaml.schemas": {"foo.json": ["*.foo"]}}))

    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code == 0
    updated = json.loads(settings_path.read_text())
    assert updated["editor.tabSize"] == 2
    assert updated["yaml.validate"] is True
    assert updated["yaml.schemas"]["foo.json"] == ["*.foo"]
    assert updated["yaml.schemas"]["./agent-eval/schemas/agent-eval.schema.json"] == [
        "eval.yaml",
        "examples/*.yaml",
        "**/*eval*.y*ml",
    ]


def test_schema_install_creates_backup_for_existing_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{}\n")

    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code == 0
    backups = list((tmp_path / ".vscode").glob("settings.json.bak.*"))
    assert len(backups) == 1


def test_schema_install_errors_on_invalid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{bad json")

    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output

