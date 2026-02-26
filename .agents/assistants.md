# Assistant Implementation

## Creating a New Assistant

### Required Methods

Inherit from `BaseAssistant` (`pitlane.assistants.base`) and implement all six abstract methods:

- `cli_name() -> str` — The CLI command name (e.g. `"claude"`, `"bob"`)
- `agent_type() -> str` — Assistant identifier used in YAML configs (e.g. `"claude-code"`)
- `get_cli_version() -> str | None` — Return version string from CLI, or `None` if unavailable
- `install_mcp(workspace: Path, mcp: McpServerConfig) -> None` — Write MCP server config into the workspace directory
- `run(prompt, workdir, config, logger) -> AssistantResult` — Execute the assistant and return results
- `supported_features() -> frozenset[AssistantFeature]` — Declare which optional features the assistant supports

### AssistantResult Structure

```python
AssistantResult(
    stdout="",                      # raw stdout from the CLI process
    stderr="",                      # raw stderr from the CLI process
    exit_code=0,                    # process exit code
    duration_seconds=1.5,           # wall-clock time
    conversation=[                  # parsed message list
        {"role": "assistant", "content": "I created hello.py"},
        {
            "role": "assistant",
            "content": "",
            "tool_use": {"name": "write_file", "input": {...}},
        },
    ],
    token_usage={"input": 100, "output": 50},  # None if unavailable
    cost_usd=0.001,                 # None if unavailable
    tool_calls_count=3,             # None if unavailable
    timed_out=False,
)
```

### Registration

Add to `src/pitlane/assistants/__init__.py`:

```python
from .your_assistant import YourAssistant

_ASSISTANTS: dict[str, type[BaseAssistant]] = {
    ...
    "your-assistant": YourAssistant,
}
```

Add to the `AssistantType` enum in `src/pitlane/config.py`:

```python
class AssistantType(str, Enum):
    ...
    YOUR_ASSISTANT = "your-assistant"
```

### Key Considerations

- **Subprocess isolation** — Run the CLI as a subprocess via `run_command_with_live_logging` in
  `assistants/base.py`. This enforces timeouts and prevents state leakage.
- **Stream parsing** — Parse NDJSON/streaming output for real-time conversation and
  metrics. See existing assistants for examples.
- **Timeout handling** — `run_command_with_live_logging` returns `timed_out=True` when the process
  is killed. Pass it through to `AssistantResult`.
- **Error handling** — Wrap the subprocess call in try/except. On failure return an
  `AssistantResult` with `exit_code=-1` and the error in `stderr`.
- **MCP config** — `install_mcp` writes a config file into the workspace before `run`
  is called. Each assistant uses its own format (see existing assistants).

### Testing

- Unit tests: mock `run_command_with_live_logging`, test `_parse_output` and `install_mcp` directly
- E2E tests: add a class to `tests/e2e/` marked `@pytest.mark.e2e`
