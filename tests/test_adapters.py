"""Tests for the adapter system: AdapterResult, BaseAdapter, factory, and stubs."""


import pytest

from agent_eval.adapters import get_adapter
from agent_eval.adapters.base import AdapterResult, BaseAdapter
from agent_eval.adapters.claude_code import ClaudeCodeAdapter
from agent_eval.adapters.cline import ClineAdapter
from agent_eval.adapters.codex import CodexAdapter
from agent_eval.adapters.mistral_vibe import MistralVibeAdapter
from agent_eval.adapters.opencode import OpenCodeAdapter


class TestAdapterResultCreation:
    def test_adapter_result_creation(self):
        result = AdapterResult(
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

    def test_adapter_result_defaults(self):
        result = AdapterResult(
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
            ("claude-code", ClaudeCodeAdapter, "claude", "claude-code"),
            ("cline", ClineAdapter, "cline", "cline"),
            ("codex", CodexAdapter, "codex", "codex"),
            ("mistral-vibe", MistralVibeAdapter, "vibe", "mistral-vibe"),
            ("opencode", OpenCodeAdapter, "opencode", "opencode"),
        ],
    )
    def test_get_adapter_returns_correct_type(self, name, expected_type, cli, agent):
        adapter = get_adapter(name)
        assert isinstance(adapter, expected_type)
        assert isinstance(adapter, BaseAdapter)
        assert adapter.cli_name() == cli
        assert adapter.agent_type() == agent

    def test_get_adapter_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("unknown-agent")
