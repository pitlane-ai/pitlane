from pitlane.assistants.base import AssistantResult, BaseAssistant
from pitlane.assistants.bob import BobAssistant
from pitlane.assistants.claude_code import ClaudeCodeAssistant
from pitlane.assistants.mistral_vibe import MistralVibeAssistant
from pitlane.assistants.opencode import OpenCodeAssistant

_ASSISTANTS: dict[str, type[BaseAssistant]] = {
    "bob": BobAssistant,
    "claude-code": ClaudeCodeAssistant,
    "mistral-vibe": MistralVibeAssistant,
    "opencode": OpenCodeAssistant,
}


def get_assistant(assistant_name: str) -> BaseAssistant:
    cls = _ASSISTANTS.get(assistant_name)
    if cls is None:
        raise ValueError(
            f"Unknown assistant: {assistant_name!r}. "
            f"Available: {', '.join(sorted(_ASSISTANTS))}"
        )
    return cls()


__all__ = [
    "AssistantResult",
    "BaseAssistant",
    "BobAssistant",
    "ClaudeCodeAssistant",
    "MistralVibeAssistant",
    "OpenCodeAssistant",
    "get_assistant",
]
