# Workspace-Scoped Sandbox Design

**Date:** 2026-02-10  
**Status:** Design Complete

## Overview

Add strict filesystem sandboxing for assistant subprocesses so each assistant can only access its assigned task workspace directory. Sandboxing is enforced at the OS layer on macOS for all adapters via one shared execution wrapper.

This feature isolates assistant behavior from the host machine and from sibling task directories while keeping the harness process itself unsandboxed.

## Goals

- Enforce workspace-only filesystem access for assistant subprocesses.
- Apply the same sandbox behavior across all adapters.
- Keep sandboxing implementation centralized in shared command execution.
- Surface sandbox policy denials as a distinct failure class in run results and reports.
- Include blocked path details in failure output when available.

## Non-Goals (v1)

- Linux sandbox implementation (planned later).
- Windows sandbox support.
- Full policy customization beyond on/off for strict workspace mode.
- Sandboxing harness internals (assertion runner, reporting, run metadata writes).

## Design Decisions

1. Enforcement layer: OS-level sandbox wrapper around assistant subprocesses.
2. Adapter strategy: adapter-agnostic, no per-adapter sandbox logic required.
3. Platform scope: macOS only in v1.
4. Failure semantics: dedicated `sandbox_denied` failure type.
5. Path visibility: include denied path when parser can extract it.

## Configuration Model

Introduce assistant-level sandbox configuration:

- `sandbox_mode: workspace_strict | off`

Behavior:

- `workspace_strict`:
  - On macOS: enabled and required.
  - On non-macOS: fail fast with explicit unsupported-platform error.
- `off`: execute assistant command without sandbox wrapper.

Default recommendation: `workspace_strict` for safety-first behavior.

## Architecture

### Shared Sandbox Module

Add `src/agent_eval/sandbox.py` with:

- `build_macos_profile(workspace: Path, profile_path: Path) -> None`
- `wrap_command_for_sandbox(cmd: list[str], workspace: Path, sandbox_mode: str) -> list[str]`
- `parse_sandbox_denial(stderr: str) -> SandboxDenial | None`

`SandboxDenial` model fields:

- `reason: str`
- `blocked_path: str | None`

### Execution Integration

Integrate wrapper in shared subprocess path (`run_command_with_streaming`) so all adapter `run()` implementations inherit sandbox behavior.

Flow:

1. Adapter builds its normal command.
2. Shared executor checks `sandbox_mode` and platform.
3. If strict mode on macOS, executor creates sandbox profile and wraps command with `sandbox-exec`.
4. Executor streams output and returns result.

## Sandbox Policy Shape (macOS)

Policy intent:

- Allow read/write inside the task workspace directory only.
- Allow minimal required system/runtime reads needed for process startup.
- Deny reads/writes outside workspace.

Policy should avoid broad home-directory access and avoid accidental access to sibling run directories.

## Failure Handling

### Classification

Extend task/adapter result data with:

- `failure_type: none | sandbox_denied | timeout | process_error`
- `failure_detail: str | None`
- `blocked_path: str | None`

Classification rules:

- If timeout occurs: `timeout`.
- If strict sandbox is enabled and stderr matches known sandbox deny signals: `sandbox_denied`.
- Otherwise non-zero execution failures: `process_error`.
- Successful command execution: `none`.

### Assertion Behavior on Sandbox Failure

For `sandbox_denied`, mark task as failed and skip assertion evaluation with an explicit skip reason indicating assistant execution was blocked by sandbox policy.

## Reporting

Update JSON and HTML outputs:

- `results.json` includes failure fields per assistant/task.
- HTML report shows distinct status badge for `Sandbox Denied`.
- Failure detail panel includes blocked path when available.

## Testing Strategy

### Unit Tests

- Sandbox profile generation for workspace-only policy.
- Command wrapping behavior for strict vs off modes.
- Denial parser extraction of reason and blocked path.

### Integration/Runner Tests

- Strict mode on macOS applies sandbox wrapper.
- Strict mode on non-macOS returns clear unsupported error.
- Off mode bypasses wrapper.
- Denial output is classified as `sandbox_denied`.
- Assertions are skipped with reason on sandbox denial.

### Report Tests

- Sandbox-denied badge renders.
- Blocked path text renders when present.

## Rollout Plan

1. Add config support and schema updates for `sandbox_mode`.
2. Implement `sandbox.py` and shared executor integration.
3. Add failure typing through adapter/runner result models.
4. Update JSON/HTML reporting and tests.
5. Document platform support and `sandbox_mode` behavior in README/docs.

## Acceptance Criteria

- All adapter subprocesses are sandboxed to workspace on macOS when strict mode is enabled.
- Access attempts outside workspace result in `sandbox_denied` classification.
- Blocked path is included in output when provided by denial logs.
- Non-macOS strict runs fail fast with actionable error message.
- Off mode behaves as current baseline.
- Test suite covers wrapper, classification, and reporting paths.
