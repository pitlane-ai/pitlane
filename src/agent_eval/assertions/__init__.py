"""Assertion system for evaluating agent outputs."""

from agent_eval.assertions.base import AssertionResult
from agent_eval.assertions.deterministic import evaluate_assertion

__all__ = ["AssertionResult", "evaluate_assertion"]
