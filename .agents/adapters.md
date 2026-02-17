# Adapter Implementation

## Creating a New Adapter

### Required Methods

1. **`cli_name()`** - Return CLI command name (e.g., "my-assistant")
2. **`agent_type()`** - Return agent type for YAML configs (e.g., "my-assistant")
3. **`run(prompt, workdir, timeout, **kwargs)`** - Execute assistant and return `AdapterResult`

### AdapterResult Structure

```python
AdapterResult(
    conversation=[
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response}
    ],
    token_usage={
        "input_tokens": 1000,
        "output_tokens": 500,
        "total_tokens": 1500
    },
    cost_usd=0.015  # Optional
)
```

### Key Considerations

- **Subprocess isolation** - Each adapter runs as subprocess (prevents state leakage, enables timeouts)
- **Stream parsing** - Parse NDJSON/streaming output for real-time metrics (see `adapters/streaming.py`)
- **Timeout handling** - Return AdapterResult with "TIMEOUT" content on timeout
- **Error handling** - Handle command not found, network failures, API rate limits

### Registration

Add to `src/pitlane/adapters/__init__.py`:

```python
from .my_adapter import MyAdapter
__all__ = [..., "MyAdapter"]
