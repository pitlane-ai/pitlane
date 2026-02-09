# Verbose Mode Design

**Date:** 2026-02-09  
**Status:** Design Complete

## Overview

Add a `--verbose` flag to the `agent-eval run` command that enables comprehensive debug output for troubleshooting adapter command execution. Output will be streamed to stderr in real-time and saved to a debug log file.

## Requirements

- CLI flag: `--verbose` / `-v` on the `run` command
- Stream debug info to stderr in real-time
- Save same debug info to `{run_dir}/debug.log`
- Show full command context: command with args, working directory, timeout, config
- Stream stdout/stderr from adapter commands in real-time
- Focus on adapter command execution (not assertion evaluation or workspace operations)

## Architecture

### Components

1. **VerboseLogger Class** (`src/agent_eval/verbose.py`)
   - Dual-output logger: stderr + file
   - Timestamp all log entries
   - Simple interface: `logger.log(message)`

2. **BaseAdapter Enhancement**
   - Add optional `logger` parameter to `run()` method
   - Pass logger through execution chain: CLI → Runner → Adapter

3. **Subprocess Streaming**
   - Replace `subprocess.run()` with `subprocess.Popen()`
   - Use `select.select()` for real-time output streaming
   - Prefix output lines with `[stdout]` or `[stderr]`

4. **CLI Integration**
   - Add `--verbose` flag to `run` command
   - Create logger instance when flag is set
   - Pass logger to Runner

## Implementation Details

### VerboseLogger Class

```python
# src/agent_eval/verbose.py
from pathlib import Path
from datetime import datetime
import sys

class VerboseLogger:
    """Dual-output logger for verbose mode."""
    
    def __init__(self, debug_file: Path | None = None):
        self.debug_file = debug_file
        self.enabled = debug_file is not None
    
    def log(self, message: str):
        """Log message to stderr and debug file."""
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

### BaseAdapter Changes

```python
# src/agent_eval/adapters/base.py
from agent_eval.verbose import VerboseLogger

class BaseAdapter(ABC):
    @abstractmethod
    def run(
        self, 
        prompt: str, 
        workdir: Path, 
        config: dict[str, Any],
        logger: VerboseLogger | None = None
    ) -> AdapterResult:
        """Execute the agent with the given prompt in workdir."""
        ...
```

### ClaudeCodeAdapter Streaming

```python
# src/agent_eval/adapters/claude_code.py
import select

def run(self, prompt: str, workdir: Path, config: dict[str, Any], 
        logger: VerboseLogger | None = None) -> AdapterResult:
    cmd = self._build_command(prompt, config)
    
    # Log command context
    if logger:
        logger.log(f"Command: {' '.join(cmd)}")
        logger.log(f"Working directory: {workdir}")
        logger.log(f"Timeout: {config.get('timeout', 300)}s")
        logger.log(f"Config: {json.dumps(config, indent=2)}")
    
    start = time.monotonic()
    
    # Use Popen for real-time streaming
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
    while proc.poll() is None:
        readable, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.1)
        for stream in readable:
            line = stream.readline()
            if line:
                if stream == proc.stdout:
                    stdout_lines.append(line)
                    if logger:
                        logger.log(f"[stdout] {line.rstrip()}")
                else:
                    stderr_lines.append(line)
                    if logger:
                        logger.log(f"[stderr] {line.rstrip()}")
    
    # Capture any remaining output
    remaining_out, remaining_err = proc.communicate()
    if remaining_out:
        stdout_lines.append(remaining_out)
        if logger:
            for line in remaining_out.splitlines():
                logger.log(f"[stdout] {line}")
    if remaining_err:
        stderr_lines.append(remaining_err)
        if logger:
            for line in remaining_err.splitlines():
                logger.log(f"[stderr] {line}")
    
    duration = time.monotonic() - start
    stdout = ''.join(stdout_lines)
    stderr = ''.join(stderr_lines)
    
    if logger:
        logger.log(f"Command completed in {duration:.2f}s with exit code {proc.returncode}")
    
    # Parse and return as before
    conversation, token_usage, cost = self._parse_output(stdout)
    return AdapterResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=proc.returncode,
        duration_seconds=duration,
        conversation=conversation,
        token_usage=token_usage,
        cost_usd=cost,
    )
```

### CLI Changes

```python
# src/agent_eval/cli.py
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
    logger = None
    if verbose:
        # Run dir will be created by Runner, so we'll pass logger to Runner
        # and let it set the debug_file path after creating run_dir
        logger = VerboseLogger()
    
    runner = Runner(
        config=eval_config,
        output_dir=Path(output_dir),
        task_filter=task,
        assistant_filter=assistant,
        logger=logger,
    )

    typer.echo("Starting evaluation run...")
    run_dir = runner.execute()
    
    # ... rest of command
```

### Runner Changes

```python
# src/agent_eval/runner.py
class Runner:
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
        run_dir = self._create_run_dir()
        
        # Set debug file path if logger exists
        if self.logger:
            self.logger.debug_file = run_dir / "debug.log"
            self.logger.log("Starting evaluation run")
        
        # ... pass self.logger to adapter.run() calls
```

## Testing Strategy

1. Manual testing with `--verbose` flag
2. Verify debug.log file is created and contains expected output
3. Test with different adapters (claude, codex, cline, etc.)
4. Verify real-time streaming works (doesn't wait for command completion)
5. Test timeout scenarios

## Future Enhancements

- Add verbosity levels (`-v`, `-vv`, `-vvv`)
- Add assertion evaluation logging (when requested)
- Add workspace operation logging (when requested)
- Colorize output for better readability
