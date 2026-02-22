from pitlane.adapters.base import AdapterResult, BaseAdapter
from pitlane.adapters.bob import BobAdapter
from pitlane.adapters.claude_code import ClaudeCodeAdapter
from pitlane.adapters.cline import ClineAdapter
from pitlane.adapters.codex import CodexAdapter
from pitlane.adapters.copilot import CopilotAdapter
from pitlane.adapters.gemini import GeminiAdapter
from pitlane.adapters.kilo import KiloAdapter
from pitlane.adapters.mistral_vibe import MistralVibeAdapter
from pitlane.adapters.opencode import OpenCodeAdapter

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "bob": BobAdapter,
    "claude-code": ClaudeCodeAdapter,
    "cline": ClineAdapter,
    "codex": CodexAdapter,
    "copilot": CopilotAdapter,
    "gemini": GeminiAdapter,
    "kilo": KiloAdapter,
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
    "BobAdapter",
    "ClaudeCodeAdapter",
    "ClineAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "GeminiAdapter",
    "KiloAdapter",
    "MistralVibeAdapter",
    "OpenCodeAdapter",
    "get_adapter",
]
