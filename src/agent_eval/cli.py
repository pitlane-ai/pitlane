from __future__ import annotations

from pathlib import Path
import sys

import typer

app = typer.Typer(name="agent-eval", help="Evaluate AI coding assistants")
schema_app = typer.Typer(name="schema", help="Generate and install schema tooling")
app.add_typer(schema_app, name="schema")


@app.command()
def run(
    config: str = typer.Argument(help="Path to eval YAML config"),
    task: str | None = typer.Option(None, help="Run only this task"),
    assistant: str | None = typer.Option(None, help="Run only this assistant"),
    output_dir: str = typer.Option("runs", help="Output directory for run results"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug output to terminal"),
    parallel: int = typer.Option(1, "--parallel", "-p", min=1, max=100, help="Number of parallel tasks to run"),
):
    """Run evaluation tasks against configured assistants."""
    from agent_eval.config import load_config
    from agent_eval.runner import Runner
    from agent_eval.reporting.html import generate_report
    import json

    config_path = Path(config)
    if not config_path.exists():
        typer.echo(f"Error: config file not found: {config}", err=True)
        raise typer.Exit(1)

    eval_config = load_config(config_path)

    runner = Runner(
        config=eval_config,
        output_dir=Path(output_dir),
        task_filter=task,
        assistant_filter=assistant,
        verbose=verbose,
        parallel_tasks=parallel,
    )

    typer.echo("Starting evaluation run...")
    run_dir = runner.execute()

    if runner.interrupted:
        typer.echo("Run interrupted. Saving partial results...")

    typer.echo("Generating report...")
    report_path = generate_report(run_dir)

    if runner.interrupted:
        typer.echo(f"Partial run saved: {run_dir}")
    else:
        typer.echo(f"Run complete: {run_dir}")
    typer.echo(f"Report: {report_path}")
    if not verbose:
        typer.echo(f"Debug log: {run_dir / 'debug.log'}")

    # Exit with non-zero if any assertion failed or run was interrupted
    if runner.interrupted:
        raise typer.Exit(1)

    results = json.loads((run_dir / "results.json").read_text())
    all_passed = all(
        task_result.get("all_passed", False)
        for assistant_results in results.values()
        for task_result in assistant_results.values()
    )
    if not all_passed:
        raise typer.Exit(1)


@app.command()
def report(
    run_dir: str = typer.Argument(help="Path to run output directory"),
):
    """Regenerate HTML report from a previous run."""
    from agent_eval.reporting.html import generate_report

    run_path = Path(run_dir)
    if not run_path.exists() or not (run_path / "results.json").exists():
        typer.echo(f"Error: not a valid run directory: {run_dir}", err=True)
        raise typer.Exit(1)

    report_path = generate_report(run_path)
    typer.echo(f"Report generated: {report_path}")


@app.command()
def init(
    dir: str = typer.Option("agent-eval", "--dir", help="Directory to initialize eval project in"),
):
    """Initialize a new eval project with example config."""
    project_dir = Path(dir)

    # Create the project directory if it doesn't exist
    if not project_dir.exists():
        project_dir.mkdir(parents=True, exist_ok=True)

    example = project_dir / "eval.yaml"
    if example.exists():
        typer.echo(f"eval.yaml already exists in {dir}, skipping.")
        return

    example.write_text("""\
assistants:
  claude-baseline:
    adapter: claude-code
    args:
      model: sonnet

tasks:
  - name: hello-world
    prompt: "Create a Python script called hello.py that prints 'Hello, World!'"
    workdir: ./fixtures/empty
    timeout: 120
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "python3 hello.py"
""")

    fixtures = project_dir / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / ".gitkeep").write_text("")

    typer.echo(f"Initialized eval project in {dir}:")
    typer.echo("  eval.yaml        - example eval config")
    typer.echo("  fixtures/empty/  - empty fixture directory")


@schema_app.command("generate")
def schema_generate(
    dir: str = typer.Option("agent-eval", "--dir", help="Project directory for default schema/doc outputs"),
    out: str | None = typer.Option(
        None, help="Output path for JSON Schema (defaults to <dir>/schemas/agent-eval.schema.json)"
    ),
    doc: str | None = typer.Option(
        None, help="Output path for schema docs (defaults to <dir>/docs/schema.md)"
    ),
):
    """Generate JSON Schema and docs for the eval YAML format."""
    from agent_eval.schema import write_json_schema, write_schema_doc

    project_dir = Path(dir)
    out_path = Path(out) if out is not None else project_dir / "schemas" / "agent-eval.schema.json"
    doc_path = Path(doc) if doc is not None else project_dir / "docs" / "schema.md"
    write_json_schema(out_path)
    write_schema_doc(doc_path)
    typer.echo(f"Wrote schema: {out_path}")
    typer.echo(f"Wrote docs: {doc_path}")


@schema_app.command("install")
def schema_install(
    dir: str = typer.Option("agent-eval", "--dir", help="Project directory for default outputs and editor settings"),
    out: str | None = typer.Option(
        None, help="Output path for JSON Schema (defaults to <dir>/schemas/agent-eval.schema.json)"
    ),
    doc: str | None = typer.Option(
        None, help="Output path for schema docs (defaults to <dir>/docs/schema.md)"
    ),
    settings: str | None = typer.Option(
        None, help="VS Code settings file to update (defaults to .vscode/settings.json)"
    ),
    schema_ref: str | None = typer.Option(
        None,
        help="Schema reference path to write under yaml.schemas (defaults to relative path of --out)",
    ),
    editor: str = typer.Option(
        "vscode",
        "--editor",
        help="Editor integration target (currently only: vscode)",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Disable interactive prompts; requires --yes to apply changes",
    ),
    yes: bool = typer.Option(False, "--yes", help="Apply changes without interactive confirmation"),
    backup: bool = typer.Option(
        True,
        "--backup/--no-backup",
        help="Create a backup before writing settings.json",
    ),
    backup_file: str | None = typer.Option(
        None, help="Optional explicit backup path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print planned changes without writing settings"
    ),
):
    """Generate schema/docs and install VS Code YAML schema settings safely."""
    from agent_eval.editor import (
        create_backup,
        default_backup_path,
        load_vscode_settings,
        plan_vscode_settings_update,
        write_json_atomic,
    )
    from agent_eval.schema import write_json_schema, write_schema_doc

    project_dir = Path(dir)
    out_path = Path(out) if out is not None else project_dir / "schemas" / "agent-eval.schema.json"
    doc_path = Path(doc) if doc is not None else project_dir / "docs" / "schema.md"
    settings_path = Path(settings) if settings is not None else Path(".vscode") / "settings.json"
    if schema_ref is None:
        if out_path.is_absolute():
            try:
                rel_out = out_path.relative_to(Path.cwd())
                schema_ref_value = f"./{rel_out.as_posix()}"
            except ValueError:
                schema_ref_value = out_path.as_posix()
        else:
            schema_ref_value = f"./{out_path.as_posix()}"
    else:
        schema_ref_value = schema_ref
    if editor != "vscode":
        typer.echo(
            f"Error: unsupported editor '{editor}'. Supported values: vscode",
            err=True,
        )
        raise typer.Exit(1)

    write_json_schema(out_path)
    write_schema_doc(doc_path)
    typer.echo(f"Wrote schema: {out_path}")
    typer.echo(f"Wrote docs: {doc_path}")

    try:
        current_settings, had_settings_file = load_vscode_settings(settings_path)
        update_plan = plan_vscode_settings_update(current_settings, schema_ref_value)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Will update VS Code settings file: {settings_path}")
    for line in update_plan.preview_lines:
        typer.echo(line)
    if not update_plan.changed:
        typer.echo("No settings changes are required.")
        return

    chosen_backup_path: Path | None = None
    if had_settings_file and backup:
        chosen_backup_path = (
            Path(backup_file) if backup_file is not None else default_backup_path(settings_path)
        )
        typer.echo(f"Backup will be created at: {chosen_backup_path}")
    elif not had_settings_file:
        typer.echo("No existing settings file found, so no backup is needed.")
    elif not backup:
        typer.echo("Backup creation disabled via --no-backup.")

    if dry_run:
        typer.echo("Dry run enabled, no settings were written.")
        return

    is_non_interactive = non_interactive or (not sys.stdin.isatty())
    if not yes:
        if is_non_interactive:
            typer.echo(
                "Error: non-interactive mode requires --yes to update settings.",
                err=True,
            )
            raise typer.Exit(1)
        if not typer.confirm("Proceed with updating VS Code settings?", default=False):
            typer.echo("Aborted. No changes were written.")
            raise typer.Exit(1)

    if chosen_backup_path is not None:
        create_backup(settings_path, chosen_backup_path)
        typer.echo(f"Wrote backup: {chosen_backup_path}")

    write_json_atomic(settings_path, update_plan.updated)
    typer.echo(f"Updated VS Code settings: {settings_path}")
