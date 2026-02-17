from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.claude_code import ClaudeCodeAdapter
from pitlane.adapters.mistral_vibe import MistralVibeAdapter
from pitlane.adapters.opencode import OpenCodeAdapter

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "mistral-vibe": MistralVibeAdapter,
    "opencode": OpenCodeAdapter,
}


def get_adapter(adapter_name: str) -> BaseAdapter:
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
    "MistralVibeAdapter",
    "OpenCodeAdapter",
    "get_adapter",
]
