"""Fixtures for E2E tests that invoke real AI assistants."""

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


def run_with_tee(cmd, *, timeout):
    """Run a subprocess, streaming output while capturing it for assertions."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    stdout_lines, stderr_lines = [], []

    def _reader(stream, buf, dest):
        for line in stream:
            buf.append(line)
            dest.write(line)
            dest.flush()

    t_out = threading.Thread(
        target=_reader, args=(proc.stdout, stdout_lines, sys.stdout)
    )
    t_err = threading.Thread(
        target=_reader, args=(proc.stderr, stderr_lines, sys.stderr)
    )
    t_out.start()
    t_err.start()
    proc.wait(timeout=timeout)
    t_out.join()
    t_err.join()

    return SimpleNamespace(
        returncode=proc.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )


def _assert_cli_installed(cli_name: str) -> None:
    """Assert that a CLI is installed; call pytest.fail() (not skip) if missing."""
    if shutil.which(cli_name) is None:
        pytest.fail(
            f"CLI '{cli_name}' not found in PATH. Install it before running E2E tests.",
            pytrace=False,
        )


def pytest_sessionstart(session) -> None:
    for cli in ("claude", "bob", "opencode", "vibe", "pitlane"):
        _assert_cli_installed(cli)


def run_pipeline(
    tmp_path_factory,
    eval_yaml_name,
    replacements=None,
    parallelism=4,
    extra_args=None,
    timeout=600,
):
    """Read eval YAML from fixtures, apply replacements, run pitlane run.

    Returns (result, run_dir) where result has .returncode/.stdout/.stderr
    and run_dir is the Path to the single output directory created.
    """
    output_dir = tmp_path_factory.mktemp("e2e_runs")
    config_dir = tmp_path_factory.mktemp("e2e_config")

    fixtures_src = Path(__file__).parent / "fixtures"
    config_path = config_dir / eval_yaml_name

    yaml_content = (fixtures_src / eval_yaml_name).read_text()
    if replacements:
        for placeholder, value in replacements.items():
            yaml_content = yaml_content.replace(placeholder, value)
    config_path.write_text(yaml_content)

    cmd = [
        "pitlane",
        "run",
        str(config_path),
        "--output-dir",
        str(output_dir),
        "--parallel",
        str(parallelism),
        "--no-open",
    ]
    if extra_args:
        cmd.extend(extra_args)

    result = run_with_tee(cmd, timeout=timeout)

    run_dirs = sorted(output_dir.iterdir())
    assert len(run_dirs) == 1, (
        f"Expected 1 run dir, got: {[str(d) for d in output_dir.iterdir()]}"
    )
    run_dir = run_dirs[0]

    return result, run_dir


def workspace(run_dir, assistant, task="hello-world"):
    """Return the workspace path for a given assistant and task."""
    return run_dir / assistant / task / "iter-0" / "workspace"
