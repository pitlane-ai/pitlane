import json
import pytest
from pathlib import Path
from agent_eval.adapters.cline import ClineAdapter


def test_build_command_minimal():
    adapter = ClineAdapter()
    cmd = adapter._build_command("Write code", {})
    assert cmd[0] == "cline"
    assert "-y" in cmd
    assert "--json" in cmd
    assert "Write code" in cmd


def test_build_command_with_timeout():
    adapter = ClineAdapter()
    cmd = adapter._build_command("test", {"timeout": 600})
    assert "--timeout" in cmd
    assert "600" in cmd


def test_parse_json_output():
    adapter = ClineAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Here is the code"}),
        json.dumps({"type": "tool_use", "name": "write_file", "input": {"path": "main.py"}}),
        json.dumps({"type": "result", "usage": {"input_tokens": 150, "output_tokens": 60}, "total_cost_usd": 0.003}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost = adapter._parse_output(stdout)
    assert len(conversation) == 2
    assert conversation[0]["role"] == "assistant"
    assert conversation[0]["content"] == "Here is the code"
    assert conversation[1]["tool_use"]["name"] == "write_file"
    assert token_usage["input"] == 150
    assert token_usage["output"] == 60
    assert cost == 0.003


def test_parse_empty_output():
    adapter = ClineAdapter()
    conversation, token_usage, cost = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None


def test_cli_name():
    adapter = ClineAdapter()
    assert adapter.cli_name() == "cline"
    assert adapter.agent_type() == "cline"
    assert adapter.skills_dir_name() == ".cline"
