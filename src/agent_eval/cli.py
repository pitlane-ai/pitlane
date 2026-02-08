import typer

app = typer.Typer(name="agent-eval", help="Evaluate AI coding assistants")


@app.command()
def run(config: str = typer.Argument(help="Path to eval YAML config")):
    """Run evaluation tasks against configured assistants."""
    typer.echo(f"Running eval from {config}")


@app.command()
def report(run_dir: str = typer.Argument(help="Path to run output directory")):
    """Regenerate HTML report from a previous run."""
    typer.echo(f"Generating report from {run_dir}")


@app.command()
def init():
    """Initialize a new eval project with example config."""
    typer.echo("Initialized eval project")
