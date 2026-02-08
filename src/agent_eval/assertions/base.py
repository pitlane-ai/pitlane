"""Base data structures for the assertion system."""

from dataclasses import dataclass


@dataclass
class AssertionResult:
    """Result of evaluating a single assertion."""

    name: str
    passed: bool
    message: str
