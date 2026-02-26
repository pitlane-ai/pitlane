#!/usr/bin/env python3
"""Validation script for the hello-world task custom_script assertion.

Runs inside the workspace directory. Exits 0 on success, 1 on failure.
"""

import subprocess
import sys
from pathlib import Path

hello_py = Path("hello.py")
if not hello_py.exists():
    print("FAIL: hello.py does not exist", file=sys.stderr)
    sys.exit(1)

result = subprocess.run(
    ["python3", "hello.py"],
    capture_output=True,
    text=True,
)
output = result.stdout + result.stderr

if "Hello, World!" not in output:
    print(
        f"FAIL: expected 'Hello, World!' in output, got: {output!r}",
        file=sys.stderr,
    )
    sys.exit(1)

print("OK: hello.py exists and prints 'Hello, World!'")
sys.exit(0)
