# Debug Log Issue - Root Cause Analysis and Fix Plan

## Problem Statement
The `debug.log` files in each assistant/task directory contain similar content for every agent instead of being specific to that particular run. This causes logs from different assistants running the same task to be mixed together.

## Root Cause Analysis

### Current Implementation
In `src/agent_eval/runner.py` (lines 131-137):
```python
task_dir = workspace.parent  # task dir
task_debug_file = task_dir / "debug.log"

task_logger = setup_logger(
    debug_file=task_debug_file,
    verbose=self.verbose,
    logger_name=f"agent_eval_task_{task_debug_file.parent.stem}"
)
```

### The Problem
1. **Logger Name Collision**: The logger name is generated as `f"agent_eval_task_{task_debug_file.parent.stem}"`, where `task_debug_file.parent.stem` is just the task name (e.g., "fibonacci-module")

2. **Shared Logger Instance**: Python's `logging.getLogger(name)` returns the same logger instance for the same name globally. When multiple assistants run the same task:
   - `claude-baseline/fibonacci-module` creates logger: `"agent_eval_task_fibonacci-module"`
   - `vibe-baseline/fibonacci-module` creates logger: `"agent_eval_task_fibonacci-module"` (SAME NAME!)

3. **Handler Replacement**: In `verbose.py` line 23, `logger.handlers.clear()` clears all handlers for that logger instance. When the second assistant starts, it:
   - Gets the same logger instance
   - Clears the handlers (removing claude's file handler)
   - Adds its own file handler pointing to vibe's debug.log
   - Now ALL logs go to vibe's debug.log, including claude's remaining logs

4. **Parallel Execution**: With `ThreadPoolExecutor`, multiple tasks run concurrently, making this race condition even worse

## Directory Structure Example
```
runs/2026-02-10_142347/
├── debug.log                                    # Main run log
├── claude-baseline/
│   └── fibonacci-module/
│       ├── debug.log                            # Should be claude-specific
│       └── workspace/
└── vibe-baseline/
    └── fibonacci-module/
        ├── debug.log                            # Should be vibe-specific
        └── workspace/
```

## Solution

### Fix: Make Logger Names Unique Per Assistant+Task

Change the logger name generation to include both assistant and task:

**In `src/agent_eval/runner.py` line 137:**
```python
# BEFORE (buggy):
logger_name=f"agent_eval_task_{task_debug_file.parent.stem}"

# AFTER (fixed):
logger_name=f"agent_eval_{assistant_name}_{task.name}"
```

This ensures each assistant+task combination gets its own logger instance:
- `"agent_eval_claude-baseline_fibonacci-module"`
- `"agent_eval_vibe-baseline_fibonacci-module"`

### Why This Works
1. Each logger instance is truly independent
2. Handler clearing only affects that specific assistant+task combination
3. Parallel execution is safe - no shared state
4. Logs are correctly isolated per assistant/task directory

## Implementation Steps

1. ✅ Identify root cause (logger name collision)
2. ⬜ Update logger name generation in `runner.py`
3. ⬜ Test with parallel execution of multiple assistants
4. ⬜ Verify debug.log files contain correct, isolated content
5. ⬜ Consider adding a comment explaining the importance of unique logger names

## Testing Strategy

Run the evaluation with multiple assistants on the same task:
```bash
agent-eval run examples/simple-codegen-eval.yaml
```

Then verify:
- Each `debug.log` contains only logs for that specific assistant+task
- No log mixing between different assistants
- Parallel execution works correctly
- Main `debug.log` still contains high-level orchestration logs

## Additional Considerations

### Alternative Solutions Considered
1. **Use file locks**: Too complex, performance overhead
2. **Disable logger caching**: Would break Python's logging design
3. **Use separate processes**: Overkill, current threading model is fine
4. **Unique logger per call**: Current fix is simpler and sufficient

### Propagation Check
The logger is passed to adapters which pass it to `run_command_with_streaming()`. Since we're fixing the logger name at creation time, all downstream usage automatically benefits from the fix.
