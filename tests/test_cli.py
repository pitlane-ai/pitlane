import json
from pathlib import Path
from typer.testing import CliRunner
from pitlane.cli import app

runner = CliRunner()


def test_init_creates_example_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "pitlane" / "eval.yaml").exists()
    assert (tmp_path / "pitlane" / "fixtures" / "empty" / ".gitkeep").exists()


def test_init_with_custom_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--dir", "my-custom-dir"])
    assert result.exit_code == 0
    assert (tmp_path / "my-custom-dir" / "eval.yaml").exists()
    assert (tmp_path / "my-custom-dir" / "fixtures" / "empty" / ".gitkeep").exists()


def test_init_with_examples_copies_examples(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--with-examples"])
    assert result.exit_code == 0
    assert (tmp_path / "pitlane" / "examples" / "simple-codegen-eval.yaml").exists()


def test_init_without_examples_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert not (tmp_path / "pitlane" / "examples").exists()


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
    assert (tmp_path / "pitlane" / "schemas" / "pitlane.schema.json").exists()
    assert (tmp_path / "pitlane" / "docs" / "schema.md").exists()


def test_schema_install_requires_yes_in_non_interactive_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["schema", "install"])
    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert (tmp_path / "pitlane" / "schemas" / "pitlane.schema.json").exists()
    assert (tmp_path / "pitlane" / "docs" / "schema.md").exists()
    assert not (tmp_path / ".vscode" / "settings.json").exists()


def test_schema_install_writes_settings_and_preserves_unrelated_keys(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"editor.tabSize": 2, "yaml.schemas": {"foo.json": ["*.foo"]}})
    )

    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code == 0
    updated = json.loads(settings_path.read_text())
    assert updated["editor.tabSize"] == 2
    assert updated["yaml.validate"] is True
    assert updated["yaml.schemas"]["foo.json"] == ["*.foo"]
    assert updated["yaml.schemas"]["./pitlane/schemas/pitlane.schema.json"] == [
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


# ============================================================================
# Run Command Error Handling Tests
# ============================================================================


def test_run_command_with_invalid_config(tmp_path, monkeypatch):
    """Test run command with a config file that has invalid YAML."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("invalid: yaml: content: [")

    result = runner.invoke(app, ["run", str(config_file)])
    assert result.exit_code != 0


def test_run_command_with_missing_adapter(tmp_path, monkeypatch):
    """Test run command when adapter is not found."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: nonexistent-adapter
    args: {}

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(app, ["run", str(config_file)])
    assert result.exit_code != 0


def test_run_command_with_adapter_error(tmp_path, monkeypatch, mocker):
    """Test run command when adapter execution fails."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    # Mock the Runner to simulate an adapter error
    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = False
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    # Create a minimal junit.xml with failures
    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="1" errors="0">
    <testcase name="test-assistant" classname="test-task">
      <failure message="Adapter error">Test failed</failure>
    </testcase>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    result = runner.invoke(app, ["run", str(config_file), "--no-open"])
    assert result.exit_code == 1


def test_run_command_with_assertion_error(tmp_path, monkeypatch, mocker):
    """Test run command when assertions fail."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "nonexistent.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    # Mock the Runner to simulate assertion failures
    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = False
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    # Create a junit.xml with assertion failures
    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="1" errors="0">
    <testcase name="test-assistant" classname="test-task">
      <failure message="Assertion failed">File does not exist</failure>
    </testcase>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    result = runner.invoke(app, ["run", str(config_file), "--no-open"])
    assert result.exit_code == 1


def test_run_command_with_workspace_error(tmp_path, monkeypatch):
    """Test run command when workspace directory doesn't exist."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./nonexistent-fixtures
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    result = runner.invoke(app, ["run", str(config_file)])
    assert result.exit_code != 0


def test_run_command_with_keyboard_interrupt(tmp_path, monkeypatch, mocker):
    """Test run command handles KeyboardInterrupt gracefully."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    # Mock the Runner to simulate interrupted execution
    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = True
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="0" failures="0" errors="0">
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    result = runner.invoke(app, ["run", str(config_file), "--no-open"])
    assert result.exit_code == 1
    assert (
        "interrupted" in result.output.lower()
        or "partial" in result.output.lower()
    )


# ============================================================================
# Run Command Options Tests
# ============================================================================


def test_run_command_with_verbose_flag(tmp_path, monkeypatch, mocker):
    """Test run command with verbose flag."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = False
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="0" errors="0">
    <testcase name="test-assistant" classname="test-task"/>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    result = runner.invoke(
        app, ["run", str(config_file), "--verbose", "--no-open"]
    )

    # Verify verbose flag was passed to Runner
    call_kwargs = mock_runner_class.call_args[1]
    assert call_kwargs["verbose"] is True
    assert result.exit_code == 0


def test_run_command_with_no_open_flag(tmp_path, monkeypatch, mocker):
    """Test run command with --no-open flag doesn't open browser."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = False
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="0" errors="0">
    <testcase name="test-assistant" classname="test-task"/>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    mock_browser = mocker.patch("webbrowser.open")
    result = runner.invoke(app, ["run", str(config_file), "--no-open"])
    assert result.exit_code == 0
    # Browser should not be opened
    mock_browser.assert_not_called()


def test_run_command_opens_browser_by_default(tmp_path, monkeypatch, mocker):
    """Test run command opens browser by default (without --no-open)."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = False
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="0" errors="0">
    <testcase name="test-assistant" classname="test-task"/>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    mock_browser = mocker.patch("webbrowser.open")
    result = runner.invoke(app, ["run", str(config_file)])
    assert result.exit_code == 0
    # Browser should be opened
    mock_browser.assert_called_once()


def test_run_command_with_all_options_combined(tmp_path, monkeypatch, mocker):
    """Test run command with multiple options combined."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "eval.yaml"
    config_file.write_text("""
assistants:
  test-assistant:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: test-task
    prompt: "Test prompt"
    workdir: ./fixtures/empty
    timeout: 60
    assertions:
      - file_exists: "test.txt"
""")

    fixtures = tmp_path / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)

    mock_runner_class = mocker.patch("pitlane.runner.Runner")
    mock_runner = mocker.Mock()
    mock_runner.interrupted = False
    mock_runner.execute.return_value = tmp_path / "runs" / "test-run"
    mock_runner_class.return_value = mock_runner

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="0" errors="0">
    <testcase name="test-assistant" classname="test-task"/>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    result = runner.invoke(
        app,
        [
            "run",
            str(config_file),
            "--verbose",
            "--no-open",
            "--parallel",
            "2",
            "--repeat",
            "3",
            "--task",
            "test-task",
            "--assistant",
            "test-assistant",
            "--output-dir",
            "custom-runs",
        ],
    )

    # Verify all options were passed correctly
    call_kwargs = mock_runner_class.call_args[1]
    assert call_kwargs["verbose"] is True
    assert call_kwargs["parallel_tasks"] == 2
    assert call_kwargs["repeat"] == 3
    assert call_kwargs["task_filter"] == "test-task"
    assert call_kwargs["assistant_filter"] == "test-assistant"
    assert call_kwargs["output_dir"] == Path("custom-runs")
    assert result.exit_code == 0


# ============================================================================
# Report Command Tests
# ============================================================================


def test_report_command_with_invalid_directory():
    """Test report command with invalid run directory."""
    result = runner.invoke(app, ["report", "/tmp/nonexistent-run-dir-12345"])
    assert result.exit_code != 0
    assert "not a valid run directory" in result.output


def test_report_command_with_open_flag(tmp_path, mocker):
    """Test report command with --open flag."""
    run_dir = tmp_path / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="0" errors="0">
    <testcase name="test-assistant" classname="test-task"/>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    mock_browser = mocker.patch("webbrowser.open")
    result = runner.invoke(app, ["report", str(run_dir), "--open"])
    assert result.exit_code == 0
    mock_browser.assert_called_once()


def test_report_command_regeneration(tmp_path, mocker):
    """Test report command regenerates report from existing run."""
    run_dir = tmp_path / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = run_dir / "junit.xml"
    junit_xml.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="test-task" tests="1" failures="0" errors="0">
    <testcase name="test-assistant" classname="test-task"/>
  </testsuite>
</testsuites>
""")

    mock_report = mocker.patch("pitlane.reporting.junit.generate_report")
    mock_report.return_value = run_dir / "report.html"
    result = runner.invoke(app, ["report", str(run_dir)])
    assert result.exit_code == 0
    assert "Report generated" in result.output
    mock_report.assert_called_once_with(run_dir)


# ============================================================================
# Init Command Edge Cases
# ============================================================================


def test_init_with_existing_eval_yaml(tmp_path, monkeypatch):
    """Test init command when eval.yaml already exists."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / "pitlane"
    project_dir.mkdir(parents=True, exist_ok=True)
    eval_yaml = project_dir / "eval.yaml"
    eval_yaml.write_text("existing content")

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "already exists" in result.output
    # Original content should be preserved
    assert eval_yaml.read_text() == "existing content"


def test_init_with_examples_source_not_found(tmp_path, monkeypatch, mocker):
    """Test init command when examples source cannot be found."""
    monkeypatch.chdir(tmp_path)

    # Mock _examples_source to return None
    mocker.patch("pitlane.cli._examples_source", return_value=None)
    result = runner.invoke(app, ["init", "--with-examples"])
    assert result.exit_code == 1
    assert "examples not found" in result.output


# ============================================================================
# Schema Install Command Edge Cases
# ============================================================================


def test_schema_install_non_interactive_without_yes(tmp_path, monkeypatch, mocker):
    """Test schema install in non-interactive mode without --yes flag."""
    monkeypatch.chdir(tmp_path)

    # Simulate non-interactive environment
    mocker.patch("sys.stdin.isatty", return_value=False)
    result = runner.invoke(app, ["schema", "install"])
    assert result.exit_code == 1
    assert "requires --yes" in result.output


def test_schema_install_with_backup(tmp_path, monkeypatch):
    """Test schema install creates backup of existing settings."""
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text('{"editor.tabSize": 4}')

    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code == 0

    # Check that backup was created
    backups = list((tmp_path / ".vscode").glob("settings.json.bak.*"))
    assert len(backups) == 1
    assert "Wrote backup" in result.output


def test_schema_install_with_no_backup(tmp_path, monkeypatch):
    """Test schema install with --no-backup flag."""
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text('{"editor.tabSize": 4}')

    result = runner.invoke(app, ["schema", "install", "--yes", "--no-backup"])
    assert result.exit_code == 0

    # Check that no backup was created
    backups = list((tmp_path / ".vscode").glob("settings.json.bak.*"))
    assert len(backups) == 0
    assert "Backup creation disabled" in result.output


def test_schema_install_dry_run(tmp_path, monkeypatch):
    """Test schema install with --dry-run flag."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["schema", "install", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run enabled" in result.output

    # Settings file should not be created
    assert not (tmp_path / ".vscode" / "settings.json").exists()


def test_schema_install_absolute_path_schema_ref(tmp_path, monkeypatch):
    """Test schema install with absolute path for schema reference."""
    monkeypatch.chdir(tmp_path)

    # Use an absolute path for the schema output
    schema_path = tmp_path / "absolute" / "schema.json"

    result = runner.invoke(
        app,
        [
            "schema",
            "install",
            "--yes",
            "--out",
            str(schema_path),
        ],
    )
    assert result.exit_code == 0
    assert schema_path.exists()


def test_schema_install_unsupported_editor(tmp_path, monkeypatch):
    """Test schema install with unsupported editor."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["schema", "install", "--editor", "vim"])
    assert result.exit_code == 1
    assert "unsupported editor" in result.output


def test_schema_install_with_settings_validation_error(tmp_path, monkeypatch):
    """Test schema install when settings validation fails."""
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Create invalid JSON
    settings_path.write_text("{invalid json content")

    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output or "Error" in result.output


def test_schema_install_no_changes_required(tmp_path, monkeypatch):
    """Test schema install when settings already have correct values."""
    monkeypatch.chdir(tmp_path)

    # First install
    result1 = runner.invoke(app, ["schema", "install", "--yes"])
    assert result1.exit_code == 0

    # Second install should detect no changes needed
    result2 = runner.invoke(app, ["schema", "install", "--yes"])
    assert result2.exit_code == 0
    assert "No settings changes are required" in result2.output


def test_schema_install_user_confirmation_flow(tmp_path, monkeypatch):
    """Test schema install confirmation flow (covered by integration tests)."""
    # Note: The typer CliRunner doesn't properly simulate TTY for stdin.isatty(),
    # so interactive confirmation is difficult to test in unit tests.
    # This behavior is covered by the non-interactive test above and would be
    # tested in integration/manual testing.
    # This test verifies the --yes flag works correctly instead.
    monkeypatch.chdir(tmp_path)

    settings_path = tmp_path / ".vscode" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text('{"existing": "value"}')

    # Test that --yes flag bypasses confirmation
    result = runner.invoke(app, ["schema", "install", "--yes"])
    assert result.exit_code == 0
    assert "Updated VS Code settings" in result.output

    # Verify settings were actually updated
    updated_settings = json.loads(settings_path.read_text())
    assert "yaml.schemas" in updated_settings
    assert "existing" in updated_settings


# ============================================================================
# Schema Generate Command Tests
# ============================================================================


def test_schema_generate_with_custom_paths(tmp_path, monkeypatch):
    """Test schema generate with custom output paths."""
    monkeypatch.chdir(tmp_path)

    schema_out = tmp_path / "custom" / "schema.json"
    doc_out = tmp_path / "custom" / "docs.md"

    result = runner.invoke(
        app,
        [
            "schema",
            "generate",
            "--out",
            str(schema_out),
            "--doc",
            str(doc_out),
        ],
    )
    assert result.exit_code == 0
    assert schema_out.exists()
    assert doc_out.exists()
    assert "Wrote schema" in result.output
    assert "Wrote docs" in result.output
