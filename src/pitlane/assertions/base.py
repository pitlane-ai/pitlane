"""Base data structures for the assertion system."""

from dataclasses import dataclass


@dataclass
class AssertionResult:
    """Result of evaluating a single assertion.

    Attributes:
        name: Identifier for the assertion (e.g. "file_exists:hello.py").
        passed: Whether the assertion passed its threshold/condition.
        message: Human-readable detail about the result.
        score: Normalized grade contribution between 0.0 and 1.0.
            For binary assertions: 1.0 (pass) or 0.0 (fail).
            For similarity assertions with min_score: normalized as
            min(raw_score / min_score, 1.0) so that meeting the threshold
            equals 1.0 and below scales proportionally.
            For similarity assertions without min_score: the raw metric
            value (observational).
        weight: Relative importance of this assertion for weighted grade
            computation. Defaults to 1.0 (equal weight).
    """

    name: str
    passed: bool
    message: str
    score: float = 0.0
    weight: float = 1.0
