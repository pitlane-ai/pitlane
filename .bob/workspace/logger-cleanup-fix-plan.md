# Logger Cleanup Fix Plan

## Problem Analysis

The test suite is failing with `RuntimeError: Logger 'X' already exists - logger names must be unique` errors. This occurs because:

1. **Root Cause**: We added a uniqueness check in `setup_logger()` that raises `RuntimeError` if a logger name already exists in `logging.Logger.manager.loggerDict`

2. **Why It Fails**: pytest runs all tests in the same Python process, so loggers created in one test persist into subsequent tests

3. **Affected Tests**:
   - `test_verbose.py`: 4 tests using default `logger_name="agent_eval"`
   - `test_runner.py`: 4 tests creating `Runner` instances with `logger_name="agent_eval_main"`

## Solution: pytest Fixture for Logger Cleanup

### Approach

Create a pytest fixture that automatically cleans up loggers after each test. This is the cleanest solution because:

- ✅ Doesn't modify production code behavior
- ✅ Centralized cleanup logic in one place
- ✅ Works automatically for all tests
- ✅ Follows pytest best practices
- ✅ Maintains the uniqueness guarantee we want in production

### Implementation Steps

1. **Create `conftest.py` fixture** (or add to existing `conftest.py`):
   ```python
   import pytest
   import logging
   
   @pytest.fixture(autouse=True)
   def cleanup_loggers():
       """Clean up all loggers after each test to prevent name collisions."""
       yield  # Run the test
       
       # After test: clean up all loggers
       loggers_to_remove = []
       for name in logging.Logger.manager.loggerDict.keys():
           if name.startswith("agent_eval"):
               loggers_to_remove.append(name)
       
       for name in loggers_to_remove:
           logger = logging.getLogger(name)
           logger.handlers.clear()
           del logging.Logger.manager.loggerDict[name]
   ```

2. **Why this works**:
   - `autouse=True`: Runs automatically for every test
   - `yield`: Separates setup (before test) from teardown (after test)
   - Filters by `"agent_eval"` prefix to only clean up our loggers
   - Clears handlers to prevent file handle leaks
   - Removes logger from registry so `setup_logger()` can create it again

3. **Alternative: Test-specific cleanup** (if autouse is too aggressive):
   ```python
   @pytest.fixture
   def clean_logger():
       """Clean up specific logger after test."""
       yield
       # Cleanup code here
   ```
   Then use `@pytest.mark.usefixtures("clean_logger")` on affected tests.

### Files to Modify

1. **Create or update**: `tests/conftest.py`
   - Add the `cleanup_loggers` fixture

2. **No changes needed**:
   - `src/agent_eval/verbose.py` - keep the uniqueness check
   - `tests/test_verbose.py` - tests will work with fixture
   - `tests/test_runner.py` - tests will work with fixture

### Testing the Fix

After implementing:
```bash
# Run the failing tests
uv run pytest tests/test_verbose.py tests/test_runner.py -v

# Run full test suite
uv run pytest
```

Expected result: All 8 previously failing tests should pass.

## Alternative Solutions Considered

### 1. Unique Logger Names Per Test
**Approach**: Use test name or UUID in logger names
```python
logger = setup_logger(debug_file, logger_name=f"agent_eval_{test_name}")
```
**Rejected because**: Requires modifying many test files and doesn't reflect production usage

### 2. Reuse Existing Loggers
**Approach**: Change `setup_logger()` to reuse loggers instead of raising error
```python
if logger_name in logging.Logger.manager.loggerDict:
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()  # Reset handlers
    # ... reconfigure
```
**Rejected because**: Changes production behavior and could hide bugs where loggers are accidentally reused

### 3. Manual Cleanup in Each Test
**Approach**: Add teardown code in each test
```python
def test_something():
    # test code
    # cleanup
    logger.handlers.clear()
    del logging.Logger.manager.loggerDict["agent_eval"]
```
**Rejected because**: Repetitive, error-prone, and violates DRY principle

## Implementation Priority

1. ✅ Create pytest fixture in `conftest.py`
2. ✅ Test with failing test files
3. ✅ Run full test suite
4. ✅ Verify no regressions

## Success Criteria

- [ ] All 8 previously failing tests pass
- [ ] Full test suite passes (89 tests)
- [ ] No changes to production code (`verbose.py`, `runner.py`)
- [ ] Logger uniqueness check remains in place
- [ ] No file handle leaks or resource warnings
