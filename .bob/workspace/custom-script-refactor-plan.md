# Custom Script Assertion Refactor Plan

## Problem Statement

The current `custom_script` assertion has a confusing `args` field that doesn't clearly indicate these are command-line arguments for the script. Users expect a clearer separation between:
- The interpreter (e.g., `python`, `node`, `ruby`)
- Interpreter flags (e.g., `-u` for Python unbuffered output)
- The script path
- Script-specific arguments

## Proposed Solution

### New Schema Structure

```yaml
assertions:
  - custom_script:
      interpreter: python                # optional: interpreter program
      interpreter_args: ["-u"]           # optional: flags for the interpreter
      script: scripts/validate_output.py # required: path to script
      script_args: ["--strict", "--format=json"]  # optional: arguments for the script
      timeout: 60                        # optional: timeout in seconds (default: 60)
      expected_exit_code: 0              # optional: expected exit code (default: 0)
      weight: 1.0                        # optional: assertion weight (default: 1.0)
```

### Command Construction Logic

```python
# With interpreter:
# {interpreter} {interpreter_args...} {script} {script_args...}
# Example: python -u scripts/validate.py --strict --format=json

# Without interpreter (direct script execution):
# {script} {script_args...}
# Example: ./validate.sh --strict
```

### Simple String Format

For simple cases, still support string format:
```yaml
- custom_script: "./validate.sh"
```

## Implementation Steps

### 1. Update Pydantic Models (`src/agent_eval/config.py`)

**Replace:**
```python
class CustomScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    script: str
    args: list[str] = []
    timeout: int = 60
    expected_exit_code: int = 0
```

**With:**
```python
class CustomScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interpreter: str | None = None
    interpreter_args: list[str] = []
    script: str
    script_args: list[str] = []
    timeout: int = 60
    expected_exit_code: int = 0
```

### 2. Update `check_custom_script` Function (`src/agent_eval/assertions/deterministic.py`)

**Replace signature:**
```python
def check_custom_script(
    workdir: str | Path,
    script: str,
    logger: logging.Logger,
    args: list[str] | None = None,
    timeout: int = 60,
    expected_exit_code: int = 0,
) -> AssertionResult:
```

**With:**
```python
def check_custom_script(
    workdir: str | Path,
    script: str,
    logger: logging.Logger,
    interpreter: str | None = None,
    interpreter_args: list[str] | None = None,
    script_args: list[str] | None = None,
    timeout: int = 60,
    expected_exit_code: int = 0,
) -> AssertionResult:
```

**Update command construction:**
```python
# Build command parts
command_parts = []

# Add interpreter and its args
if interpreter:
    command_parts.append(shlex.quote(interpreter))
    if interpreter_args:
        command_parts.extend(shlex.quote(arg) for arg in interpreter_args)

# Add script
command_parts.append(shlex.quote(script))

# Add script args
if script_args:
    command_parts.extend(shlex.quote(arg) for arg in script_args)

command = " ".join(command_parts)

logger.info(f"Running custom_script: {command} (timeout={timeout}s, expected_exit_code={expected_exit_code})")

# Rest of function remains the same...
```

### 3. Update Dispatcher (`src/agent_eval/assertions/deterministic.py`)

**Replace:**
```python
elif atype == "custom_script":
    if isinstance(value, str):
        result = check_custom_script(workdir, value, logger)
    else:
        result = check_custom_script(
            workdir,
            value["script"],
            logger,
            args=value.get("args"),
            timeout=value.get("timeout", 60),
            expected_exit_code=value.get("expected_exit_code", 0),
        )
```

**With:**
```python
elif atype == "custom_script":
    if isinstance(value, str):
        result = check_custom_script(workdir, value, logger)
    else:
        result = check_custom_script(
            workdir,
            value["script"],
            logger,
            interpreter=value.get("interpreter"),
            interpreter_args=value.get("interpreter_args"),
            script_args=value.get("script_args"),
            timeout=value.get("timeout", 60),
            expected_exit_code=value.get("expected_exit_code", 0),
        )
```

### 4. Update Tests (`tests/test_assertions.py`)

**Replace all existing custom_script tests with:**

```python
# --- check_custom_script ---

def test_custom_script_simple_string(tmp_path):
    """Test simple custom script with string format."""
    script = tmp_path / "test_script.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    script.chmod(0o755)
    result = evaluate_assertion(tmp_path, {"custom_script": "./test_script.sh"})
    assert result.passed is True
    assert result.score == 1.0

def test_custom_script_with_interpreter(tmp_path):
    """Test custom script with interpreter."""
    script = tmp_path / "test.py"
    script.write_text("import sys; sys.exit(0)")
    
    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python",
                "script": "./test.py",
            }
        },
    )
    assert result.passed is True

def test_custom_script_with_interpreter_args(tmp_path):
    """Test custom script with interpreter and interpreter args."""
    script = tmp_path / "test.py"
    script.write_text("import sys; print('hello'); sys.exit(0)")
    
    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python",
                "interpreter_args": ["-u"],
                "script": "./test.py",
            }
        },
    )
    assert result.passed is True

def test_custom_script_with_script_args(tmp_path):
    """Test custom script with script arguments."""
    script = tmp_path / "test.py"
    script.write_text("""
import sys
if '--strict' in sys.argv and '--format=json' in sys.argv:
    sys.exit(0)
else:
    sys.exit(1)
""")
    
    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python",
                "script": "./test.py",
                "script_args": ["--strict", "--format=json"],
            }
        },
    )
    assert result.passed is True

def test_custom_script_all_options(tmp_path):
    """Test custom script with all options."""
    script = tmp_path / "test.py"
    script.write_text("""
import sys
if len(sys.argv) == 3 and sys.argv[1] == '--arg1' and sys.argv[2] == '--arg2':
    sys.exit(0)
else:
    sys.exit(1)
""")
    
    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "interpreter": "python",
                "interpreter_args": ["-u"],
                "script": "./test.py",
                "script_args": ["--arg1", "--arg2"],
                "timeout": 30,
                "expected_exit_code": 0,
            }
        },
    )
    assert result.passed is True

def test_custom_script_expected_exit_code(tmp_path):
    """Test custom script with non-zero expected exit code."""
    script = tmp_path / "test.sh"
    script.write_text("#!/bin/bash\nexit 42\n")
    script.chmod(0o755)
    
    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "script": "./test.sh",
                "expected_exit_code": 42,
            }
        },
    )
    assert result.passed is True

def test_custom_script_timeout(tmp_path):
    """Test custom script that times out."""
    script = tmp_path / "test.sh"
    script.write_text("#!/bin/bash\nsleep 10\n")
    script.chmod(0o755)
    
    result = evaluate_assertion(
        tmp_path,
        {
            "custom_script": {
                "script": "./test.sh",
                "timeout": 1,
            }
        },
    )
    assert result.passed is False
    assert "timed out" in result.message

def test_custom_script_not_found(tmp_path):
    """Test custom script that doesn't exist."""
    result = evaluate_assertion(tmp_path, {"custom_script": "nonexistent.sh"})
    assert result.passed is False
```

### 5. Update Documentation (`docs/schema.md`)

**Add section:**

```markdown
## Custom Script Assertions

Run custom validation scripts with full control over interpreter, arguments, and execution.

### Basic Usage

```yaml
assertions:
  # Simple shell script
  - custom_script: "./validate.sh"
  
  # Python script with interpreter
  - custom_script:
      interpreter: python
      script: scripts/validate_output.py
      script_args: ["--strict"]
```

### Advanced Usage

```yaml
assertions:
  # Python with interpreter flags and script args
  - custom_script:
      interpreter: python
      interpreter_args: ["-u"]  # unbuffered output
      script: scripts/validate_output.py
      script_args: ["--strict", "--format=json"]
      timeout: 120
      expected_exit_code: 0
      weight: 2.0
  
  # Node.js script
  - custom_script:
      interpreter: node
      script: validator.js
      script_args: ["--config", "strict.json"]
  
  # Ruby script expecting failure
  - custom_script:
      interpreter: ruby
      script: check_errors.rb
      expected_exit_code: 1
```

### Field Reference

- `interpreter` (optional): Interpreter program (e.g., `python`, `node`, `ruby`)
- `interpreter_args` (optional): Flags for the interpreter (e.g., `["-u"]` for Python)
- `script` (required): Path to the script file
- `script_args` (optional): Arguments to pass to the script
- `timeout` (optional): Timeout in seconds (default: 60)
- `expected_exit_code` (optional): Expected exit code (default: 0)
- `weight` (optional): Assertion weight for grading (default: 1.0)

### Command Construction

The command is built as:
```
{interpreter} {interpreter_args...} {script} {script_args...}
```

Examples:
- `python -u scripts/validate.py --strict --format=json`
- `node validator.js --config strict.json`
- `./validate.sh --strict` (no interpreter)
```

### 6. Update JSON Schema

The JSON schema will be automatically generated from the updated Pydantic models via `agent-eval schema generate`.

## Testing Strategy

1. **Unit tests** for all new parameter combinations
2. **Integration tests** with real Python, shell, and Node.js scripts
3. **Edge cases**: missing scripts, timeouts, non-zero exit codes

## Benefits

1. **Clarity**: Clear separation of interpreter, script, and arguments
2. **Flexibility**: Support for interpreter flags
3. **Simplicity**: No backward compatibility complexity
4. **Better Error Messages**: More specific error reporting
5. **Extensibility**: Easy to add new features in the future

## Breaking Change Notice

This is a **breaking change**. Users with existing `custom_script` assertions using the `args` field will need to update their configs:

**Old:**
```yaml
- custom_script:
    script: "python scripts/validate.py"
    args: ["--strict"]
```

**New:**
```yaml
- custom_script:
    interpreter: python
    script: scripts/validate.py
    script_args: ["--strict"]