# Verbose Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--verbose` flag to enable real-time debug output showing adapter command execution details, streamed to stderr and saved to debug.log.

**Architecture:** Create VerboseLogger class for dual output (stderr + file), modify BaseAdapter to accept logger parameter, update ClaudeCodeAdapter to use Popen for real-time streaming, and add CLI flag.

**Tech Stack:** Python 3.11+, subprocess.Popen, select.select for streaming, Typer for CLI

---

## Task 1: Create VerboseLogger Class

**Files:**
- Create: `src/agent_eval/verbose.py`
- Test: `tests/test_verbose.py`

**Step 1: Write the failing test**

Create `tests/test_verbose.py`:

```python
"""Tests for verbose logging."""

from pathlib import Path
from agent_eval.verbose import VerboseLogger
import tempfile


def test_verbose_logger_disabled_by_default():
    """Logger should be disabled when no debug file provided."""
    logger = VerboseLogger()
    assert not logger.enabled


def test_verbose_logger_enabled_with_file():
    """Logger should be enabled when debug file provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = VerboseLogger(debug_file=debug_file)
        assert logger.enabled


def test_verbose_logger_writes_to_file():
    """Logger should write messages to debug file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = VerboseLogger(debug_file=debug_file)
        
        logger.log("test message")
        
        content = debug_file.read_text()
        assert "test message" in content
        assert "[" in content  # timestamp


def test_verbose_logger_no_op_when_disabled():
    """Logger should not crash when disabled."""
    logger = VerboseLogger()
    logger.log("test message")  # Should not raise
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_verbose.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'agent_eval.verbose'"

**Step 3: Write minimal implementation**

Create `src/agent_eval/verbose.py`:

```python
"""Verbose logging for debug output."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys


class VerboseLogger:
    """Dual-output logger for verbose mode (stderr + file)."""

    def __init__(self, debug_file: Path | None = None):
        self.debug_file = debug_file
        self.enabled = debug_file is not None

    def log(self, message: str):
        """Log message to stderr and debug file with timestamp."""
        if not self.enabled:
            return

        timestamp = datetime.now().isoformat()
        formatted = f"[{timestamp}] {message}"

        # Write to stderr
        print(formatted, file=sys.stderr)

        # Append to debug.log
        if self.debug_file:
            with open(self.debug_file, 'a') as f:
                f.write(formatted + '\n')
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_verbose.py -v`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add src/agent_eval/verbose.py tests/test_verbose.py
git commit -m "feat: add VerboseLogger for debug output"
```

---

## Task 2: Update BaseAdapter Interface

**Files:**
- Modify: `src/agent_eval/adapters/base.py`
- Test: `tests/test_adapters.py`

**Step 1: Write the failing test**

Add to `tests/test_adapters.py`:

```python
from agent_eval.verbose import VerboseLogger


def test_base_adapter_accepts_logger():
    """BaseAdapter.run() should accept optional logger parameter."""
    from agent_eval.adapters.base import BaseAdapter
    import inspect
    
    sig = inspect.signature(BaseAdapter.run)
    assert 'logger' in sig.parameters
    param = sig.parameters['logger']
    assert param.default is None  # Optional parameter
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adapters.py::test_base_adapter_accepts_logger -v`
Expected: FAIL with "AssertionError: assert 'logger' in..."

**Step 3: Update BaseAdapter signature**

Modify `src/agent_eval/adapters/base.py`:

```python
"""Base adapter interface and AdapterResult dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_eval.verbose import VerboseLogger


@dataclass
class AdapterResult:
    """Captures the result of running an agent adapter."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    conversation: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None


class BaseAdapter(ABC):
    """Abstract base class that all agent adapters must implement."""

    @abstractmethod
    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: VerboseLogger | None = None,
    ) -> AdapterResult:
        """Execute the agent with the given prompt in workdir."""
        ...

    @abstractmethod
    def cli_name(self) -> str:
        """The CLI command name for this agent."""
        ...

    @abstractmethod
    def agent_type(self) -> str:
        """Identifier for this agent type."""
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adapters.py::test_base_adapter_accepts_logger -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent_eval/adapters/base.py tests/test_adapters.py
git commit -m "feat: add logger parameter to BaseAdapter.run()"
```

---

## Task 3: Update ClaudeCodeAdapter with Streaming

**Files:**
- Modify: `src/agent_eval/adapters/claude_code.py`
- Test: `tests/test_adapter_claude.py`

**Step 1: Write the failing test**

Add to `tests/test_adapter_claude.py`:

```python
from pathlib import Path
from agent_eval.adapters.claude_code import ClaudeCodeAdapter
from agent_eval.verbose import VerboseLogger
import tempfile


def test_claude_adapter_logs_command_when_verbose():
    """Adapter should log command details when logger provided."""
    adapter = ClaudeCodeAdapter()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_file = Path(tmpdir) / "debug.log"
        logger = VerboseLogger(debug_file=debug_file)
        workdir = Path(tmpdir) / "work"
        workdir.mkdir()
        
        # This will fail to run claude, but should log the command
        try:
            adapter.run(
                prompt="test",
                workdir=workdir,
                config={"model": "sonnet", "timeout": 1},
                logger=logger,
            )
        except Exception:
            pass  # Expected to fail
        
        content = debug_file.read_text()
        assert "Command:" in content
        assert "claude" in content
        assert "Working directory:" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adapter_claude.py::test_claude_adapter_logs_command_when_verbose -v`
Expected: FAIL (adapter doesn't accept logger yet)

**Step 3: Update ClaudeCodeAdapter with streaming**

Modify `src/agent_eval/adapters/claude_code.py`:

```python
"""Claude Code adapter."""

from __future__ import annotations

import json
import select
import subprocess
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from agent_eval.adapters.base import AdapterResult, BaseAdapter

if TYPE_CHECKING:
    from agent_eval.verbose import VerboseLogger


class ClaudeCodeAdapter(BaseAdapter):

    def cli_name(self) -> str:
        return "claude"

    def agent_type(self) -> str:
        return "claude-code"

    def _build_command(self, prompt: str, config: dict[str, Any]) -> list[str]:
        cmd = [
            "claude", "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if model := config.get("model"):
            cmd.extend(["--model", model])
        if mcp_config := config.get("mcp_config"):
            cmd.extend(["--mcp-config", mcp_config])
        if system_prompt := config.get("system_prompt"):
            cmd.extend(["--append-system-prompt", system_prompt])
        if max_turns := config.get("max_turns"):
            cmd.extend(["--max-turns", str(max_turns)])
        if max_budget := config.get("max_budget_usd"):
            cmd.extend(["--max-budget-usd", str(max_budget)])
        cmd.append(prompt)
        return cmd

    def _parse_output(self, stdout: str) -> tuple[list[dict], dict | None, float | None]:
        """Parse stream-json NDJSON output into conversation, token_usage, cost."""
        conversation: list[dict] = []
        token_usage = None
        cost = None

        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "assistant":
                message = msg.get("message", {})
                for block in message.get("content", []):
                    if block.get("type") == "text":
                        conversation.append({
                            "role": "assistant",
                            "content": block["text"],
                        })
                    elif block.get("type") == "tool_use":
                        conversation.append({
                            "role": "assistant",
                            "content": "",
                            "tool_use": {
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            },
                        })
            elif msg_type == "result":
                usage = msg.get("usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    }
                cost = msg.get("total_cost_usd")

        return conversation, token_usage, cost

    def run(
        self,
        prompt: str,
        workdir: Path,
        config: dict[str, Any],
        logger: VerboseLogger | None = None,
    ) -> AdapterResult:
        cmd = self._build_command(prompt, config)
        timeout = config.get("timeout", 300)

        # Log command context if verbose
        if logger:
            logger.log(f"Command: {' '.join(cmd)}")
            logger.log(f"Working directory: {workdir}")
            logger.log(f"Timeout: {timeout}s")
            logger.log(f"Config: {json.dumps(config, indent=2)}")

        start = time.monotonic()

        try:
            # Use Popen for real-time streaming when logger is enabled
            if logger:
                proc = subprocess.Popen(
                    cmd,
                    cwd=workdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                )

                stdout_lines = []
                stderr_lines = []

                # Stream output in real-time
                import sys
                if sys.platform != "win32":
                    # Use select on Unix-like systems
                    while proc.poll() is None:
                        readable, _, _ = select.select(
                            [proc.stdout, proc.stderr], [], [], 0.1
                        )
                        for stream in readable:
                            line = stream.readline()
                            if line:
                                if stream == proc.stdout:
                                    stdout_lines.append(line)
                                    logger.log(f"[stdout] {line.rstrip()}")
                                else:
                                    stderr_lines.append(line)
                                    logger.log(f"[stderr] {line.rstrip()}")
                else:
                    # Windows: read without select
                    import threading
                    
                    def read_stream(stream, lines, prefix):
                        for line in stream:
                            lines.append(line)
                            logger.log(f"[{prefix}] {line.rstrip()}")
                    
                    stdout_thread = threading.Thread(
                        target=read_stream, args=(proc.stdout, stdout_lines, "stdout")
                    )
                    stderr_thread = threading.Thread(
                        target=read_stream, args=(proc.stderr, stderr_lines, "stderr")
                    )
                    stdout_thread.start()
                    stderr_thread.start()
                    proc.wait(timeout=timeout)
                    stdout_thread.join()
                    stderr_thread.join()

                # Capture any remaining output
                remaining_out, remaining_err = proc.communicate()
                if remaining_out:
                    stdout_lines.append(remaining_out)
                    for line in remaining_out.splitlines():
                        logger.log(f"[stdout] {line}")
                if remaining_err:
                    stderr_lines.append(remaining_err)
                    for line in remaining_err.splitlines():
                        logger.log(f"[stderr] {line}")

                stdout = ''.join(stdout_lines)
                stderr = ''.join(stderr_lines)
                exit_code = proc.returncode

            else:
                # Use run() for non-verbose mode (existing behavior)
                proc = subprocess.run(
                    cmd,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                stdout = proc.stdout
                stderr = proc.stderr
                exit_code = proc.returncode

        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            if logger:
                logger.log(f"Command timed out after {duration:.2f}s")
            return AdapterResult(
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                exit_code=-1,
                duration_seconds=duration,
                conversation=[],
                token_usage=None,
                cost_usd=None,
            )

        duration = time.monotonic() - start

        if logger:
            logger.log(f"Command completed in {duration:.2f}s with exit code {exit_code}")

        conversation, token_usage, cost = self._parse_output(stdout)
        return AdapterResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_seconds=duration,
            conversation=conversation,
            token_usage=token_usage,
            cost_usd=cost,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adapter_claude.py::test_claude_adapter_logs_command_when_verbose -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent_eval/adapters/claude_code.py tests/test_adapter_claude.py
git commit -m "feat: add verbose logging and streaming to ClaudeCodeAdapter"
```

---

## Task 4: Update Other Adapters

**Files:**
- Modify: `src/agent_eval/adapters/codex.py`
- Modify: `src/agent_eval/adapters/cline.py`
- Modify: `src/agent_eval/adapters/mistral_vibe.py`
- Modify: `src/agent_eval/adapters/opencode.py`

**Step 1: Update each adapter signature**

For each adapter file, update the `run()` method signature to accept the logger parameter:

```python
def run(
    self,
    prompt: str,
    workdir: Path,
    config: dict[str, Any],
    logger: VerboseLogger | None = None,
) -> AdapterResult:
```

Add the TYPE_CHECKING import at the top:

```python
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_eval.verbose import VerboseLogger
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/test_adapter_codex.py tests/test_adapter_cline.py tests/test_adapter_vibe.py tests/test_adapter_opencode.py -v`
Expected: PASS (signature change should not break existing tests)

**Step 3: Commit**

```bash
git add src/agent_eval/adapters/*.py
git commit -m "feat: add logger parameter to all adapters"
```

---

## Task 5: Update Runner to Pass Logger

**Files:**
- Modify: `src/agent_eval/runner.py`

**Step 1: Update Runner class**

Modify `src/agent_eval/runner.py` to accept and use logger:

```python
"""Orchestrates evaluation execution."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_eval.config import EvalConfig
    from agent_eval.verbose import VerboseLogger


class Runner:
    """Orchestrates evaluation runs."""

    def __init__(
        self,
        config: EvalConfig,
        output_dir: Path,
        task_filter: str | None = None,
        assistant_filter: str | None = None,
        logger: VerboseLogger | None = None,
    ):
        self.config = config
        self.output_dir = output_dir
        self.task_filter = task_filter
        self.assistant_filter = assistant_filter
        self.logger = logger

    def execute(self) -> Path:
        """Execute evaluation and return run directory path."""
        run_dir = self._create_run_dir()

        # Set debug file path if logger exists
        if self.logger:
            self.logger.debug_file = run_dir / "debug.log"
            self.logger.enabled = True
            self.logger.log("Starting evaluation run")

        # ... rest of execute method, pass self.logger to adapter.run() calls
```

Find all `adapter.run()` calls and add `logger=self.logger` parameter.

**Step 2: Run existing tests**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/agent_eval/runner.py
git commit -m "feat: pass logger through Runner to adapters"
```

---

## Task 6: Add CLI Flag

**Files:**
- Modify: `src/agent_eval/cli.py`
- Test: Manual testing

**Step 1: Add --verbose flag**

Modify `src/agent_eval/cli.py`:

```python
@app.command()
def run(
    config: str = typer.Argument(help="Path to eval YAML config"),
    task: str | None = typer.Option(None, help="Run only this task"),
    assistant: str | None = typer.Option(None, help="Run only this assistant"),
    output_dir: str = typer.Option("runs", help="Output directory for run results"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug output"),
):
    """Run evaluation tasks against configured assistants."""
    from agent_eval.config import load_config
    from agent_eval.runner import Runner
    from agent_eval.reporting.html import generate_report
    from agent_eval.verbose import VerboseLogger
    import json

    config_path = Path(config)
    if not config_path.exists():
        typer.echo(f"Error: config file not found: {config}", err=True)
        raise typer.Exit(1)

    eval_config = load_config(config_path)

    # Create logger if verbose mode enabled
    logger = VerboseLogger() if verbose else None

    runner = Runner(
        config=eval_config,
        output_dir=Path(output_dir),
        task_filter=task,
        assistant_filter=assistant,
        logger=logger,
    )

    typer.echo("Starting evaluation run...")
    run_dir = runner.execute()

    typer.echo("Generating report...")
    report_path = generate_report(run_dir)

    typer.echo(f"Run complete: {run_dir}")
    typer.echo(f"Report: {report_path}")

    # Exit with non-zero if any assertion failed
    results = json.loads((run_dir / "results.json").read_text())
    all_passed = all(
        task_result.get("all_passed", False)
        for assistant_results in results.values()
        for task_result in assistant_results.values()
    )
    if not all_passed:
        raise typer.Exit(1)
```

**Step 2: Manual test**

Run: `agent-eval run examples/simple-codegen-eval.yaml --verbose`
Expected: See debug output in stderr and debug.log file created

**Step 3: Test without verbose**

Run: `agent-eval run examples/simple-codegen-eval.yaml`
Expected: Normal output, no debug.log file

**Step 4: Commit**

```bash
git add src/agent_eval/cli.py
git commit -m "feat: add --verbose flag to run command"
```

---

## Task 7: Update Documentation

**Files:**
- Modify: `README.md`

**Step 1: Add verbose flag documentation**

Add to README.md under "Running Evaluations" section:

```markdown
### Debug Mode

Enable verbose output to see detailed command execution:

```bash
# Show debug output in stderr and save to debug.log
agent-eval run examples/simple-codegen-eval.yaml --verbose

# Short form
agent-eval run examples/simple-codegen-eval.yaml -v
```

Verbose mode displays:
- Full command with all arguments
- Working directory
- Timeout settings
- Real-time stdout/stderr from adapter commands
- Execution duration and exit codes

Debug output is saved to `{run_dir}/debug.log` for post-mortem analysis.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add verbose mode documentation"
```

---

## Verification

**Final integration test:**

```bash
# Run with verbose mode
agent-eval run examples/simple-codegen-eval.yaml --verbose

# Verify:
# 1. Debug output appears in stderr
# 2. debug.log file exists in run directory
# 3. debug.log contains command details and output
# 4. Evaluation still completes successfully
```

**Run full test suite:**

```bash
uv run pytest -v
```

Expected: All tests pass
