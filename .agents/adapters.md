# Adapter Implementation

## Creating a New Adapter

### Required Methods

Inherit from `BaseAdapter` (`pitlane.adapters.base`) and implement all six abstract methods:

- `cli_name() -> str` — The CLI command name (e.g. `"claude"`, `"bob"`)
- `agent_type() -> str` — Adapter identifier used in YAML configs (e.g. `"claude-code"`)
- `get_cli_version() -> str | None` — Return version string from CLI, or `None` if unavailable
- `install_mcp(workspace: Path, mcp: McpServerConfig) -> None` — Write MCP server config into the workspace directory
- `run(prompt, workdir, config, logger) -> AdapterResult` — Execute the assistant and return results
- `supported_features() -> frozenset[AdapterFeature]` — Declare which optional features the adapter supports

### AdapterResult Structure

```python
AdapterResult(
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

Add to `src/pitlane/adapters/__init__.py`:

```python
from .your_adapter import YourAdapter

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    ...
    "your-adapter": YourAdapter,
}
```

Add to the `AdapterType` enum in `src/pitlane/config.py`:

```python
class AdapterType(str, Enum):
    ...
    YOUR_ADAPTER = "your-adapter"
```

### Key Considerations

- **Subprocess isolation** — Run the CLI as a subprocess via `run_streaming_sync` in
  `adapters/streaming.py`. This enforces timeouts and prevents state leakage.
- **Stream parsing** — Parse NDJSON/streaming output for real-time conversation and
  metrics. See existing adapters for examples.
- **Timeout handling** — `run_streaming_sync` returns `timed_out=True` when the process
  is killed. Pass it through to `AdapterResult`.
- **Error handling** — Wrap the subprocess call in try/except. On failure return an
  `AdapterResult` with `exit_code=-1` and the error in `stderr`.
- **MCP config** — `install_mcp` writes a config file into the workspace before `run`
  is called. Each adapter uses its own format (see existing adapters).

### Testing

- Unit tests: mock `run_streaming_sync`, test `_parse_output` and `install_mcp` directly
- E2E tests: add a class to `tests/test_e2e_adapters.py` marked `@pytest.mark.e2e`
