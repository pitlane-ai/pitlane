from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(name="agent-eval", help="Evaluate AI coding assistants")


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

    typer.echo("Generating report...")
    report_path = generate_report(run_dir)

    typer.echo(f"Run complete: {run_dir}")
    typer.echo(f"Report: {report_path}")
    if not verbose:
        typer.echo(f"Debug log: {run_dir / 'debug.log'}")

    # Exit with non-zero if any assertion failed
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
    prompt: "Create a Python script that prints 'Hello, World!'"
    workdir: ./fixtures/empty
    timeout: 120
    assertions:
      - file_exists: "hello.py"
      - command_succeeds: "python hello.py"
""")

    fixtures = project_dir / "fixtures/empty"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / ".gitkeep").write_text("")

    typer.echo(f"Initialized eval project in {dir}:")
    typer.echo("  eval.yaml        - example eval config")
    typer.echo("  fixtures/empty/  - empty fixture directory")


@app.command()
def schema(
    out: str = typer.Option(
        "schemas/agent-eval.schema.json", help="Output path for JSON Schema"
    ),
    doc: str = typer.Option("docs/schema.md", help="Output path for schema docs"),
):
    """Generate JSON Schema and docs for the eval YAML format."""
    from agent_eval.schema import write_json_schema, write_schema_doc

    out_path = Path(out)
    doc_path = Path(doc)
    write_json_schema(out_path)
    write_schema_doc(doc_path)
    typer.echo(f"Wrote schema: {out_path}")
    typer.echo(f"Wrote docs: {doc_path}")
