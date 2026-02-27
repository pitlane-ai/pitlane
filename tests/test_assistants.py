import pytest

from pitlane.assistants import get_assistant
from pitlane.assistants.base import AssistantResult, BaseAssistant
from pitlane.assistants.claude_code import ClaudeCodeAssistant
from pitlane.assistants.mistral_vibe import MistralVibeAssistant
from pitlane.assistants.opencode import OpenCodeAssistant


class TestAssistantResultCreation:
    def test_assistant_result_creation(self):
        result = AssistantResult(
            stdout="hello",
            stderr="err",
            exit_code=0,
            duration_seconds=1.5,
            conversation=[{"role": "user", "content": "hi"}],
            token_usage={"input": 10, "output": 20},
            cost_usd=0.01,
        )
        assert result.stdout == "hello"
        assert result.stderr == "err"
        assert result.exit_code == 0
        assert result.duration_seconds == 1.5
        assert result.conversation == [{"role": "user", "content": "hi"}]
        assert result.token_usage == {"input": 10, "output": 20}
        assert result.cost_usd == 0.01

    def test_assistant_result_defaults(self):
        result = AssistantResult(
            stdout="out",
            stderr="",
            exit_code=0,
            duration_seconds=0.5,
        )
        assert result.conversation == []
        assert result.token_usage is None
        assert result.cost_usd is None


class TestGetAdapter:
    @pytest.mark.parametrize(
        "name,expected_type,cli,agent",
        [
            ("claude-code", ClaudeCodeAssistant, "claude", "claude-code"),
            ("mistral-vibe", MistralVibeAssistant, "vibe", "mistral-vibe"),
            ("opencode", OpenCodeAssistant, "opencode", "opencode"),
        ],
    )
    def test_get_assistant_returns_correct_type(self, name, expected_type, cli, agent):
        adapter = get_assistant(name)
        assert isinstance(adapter, expected_type)
        assert isinstance(adapter, BaseAssistant)
        assert adapter.cli_name() == cli
        assert adapter.agent_type() == agent

    def test_get_assistant_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown assistant"):
            get_assistant("unknown-agent")
