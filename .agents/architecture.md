# Architecture & Design

## Key Design Decisions

### Subprocess-Based Execution

Each assistant runs as a subprocess for isolation. This prevents state leakage and enables timeout enforcement, but requires CLI tools to be installed.

### Stream-Based Parsing

Parse NDJSON/streaming output for real-time metrics. See `assistants/base.py` for implementation.

### Workspace Isolation

Each task runs in a clean workspace copy to prevent cross-contamination. See `workspace.py`.

### Exit Code Semantics

CLI exits non-zero if any assertion fails (enables CI/CD integration).

### Schema Generation

Generate schema and docs from Pydantic models (single source of truth). Run `pitlane schema generate`.
