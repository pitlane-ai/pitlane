# pitlane YAML Schema

This doc is generated from the Pydantic models.

## Top-level keys

- `assistants`: mapping of assistant names to config.
- `tasks`: list of task definitions.

## Assistant Config

- `type`: string (required) - one of: bob, claude-code, mistral-vibe, opencode
- `args`: object (optional) - assistant-specific arguments
- `skills`: array (optional) - list of skill references

## Assertions

- `file_exists`: string
- `file_contains`: { path, pattern }
- `command_succeeds`: string
- `command_fails`: string
- `custom_script`: string or { interpreter, interpreter_args, script, script_args, timeout, expected_exit_code }
- `bleu`: { actual, expected, metric, min_score }
- `rouge`: { actual, expected, metric, min_score }
- `bertscore`: { actual, expected, metric, min_score }
- `cosine_similarity`: { actual, expected, metric, min_score }

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
