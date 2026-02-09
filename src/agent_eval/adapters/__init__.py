"""Adapter system for agent-eval."""

from agent_eval.adapters.base import AdapterResult, BaseAdapter
from agent_eval.adapters.claude_code import ClaudeCodeAdapter
from agent_eval.adapters.cline import ClineAdapter
from agent_eval.adapters.codex import CodexAdapter
from agent_eval.adapters.mistral_vibe import MistralVibeAdapter
from agent_eval.adapters.opencode import OpenCodeAdapter

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "cline": ClineAdapter,
    "codex": CodexAdapter,
    "mistral-vibe": MistralVibeAdapter,
    "opencode": OpenCodeAdapter,
}


def get_adapter(adapter_name: str) -> BaseAdapter:
    """Factory that returns the appropriate adapter instance.

    Raises ValueError for unknown adapter names.
    """
    cls = _ADAPTERS.get(adapter_name)
    if cls is None:
        raise ValueError(
            f"Unknown adapter: {adapter_name!r}. "
            f"Available: {', '.join(sorted(_ADAPTERS))}"
        )
    return cls()


__all__ = [
    "AdapterResult",
    "BaseAdapter",
    "ClaudeCodeAdapter",
    "ClineAdapter",
    "CodexAdapter",
    "MistralVibeAdapter",
    "OpenCodeAdapter",
    "get_adapter",
]
