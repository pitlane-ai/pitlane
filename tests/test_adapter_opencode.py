import json
import pytest
from pathlib import Path
from agent_eval.adapters.opencode import OpenCodeAdapter


def test_build_command_minimal():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command("Write code", {})
    assert cmd[0] == "opencode"
    assert "run" in cmd
    assert "--format" in cmd
    assert "json" in cmd
    assert "Write code" in cmd


def test_build_command_with_model():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command("test", {"model": "anthropic/claude-sonnet-4-5-20250929"})
    assert "--model" in cmd
    assert "anthropic/claude-sonnet-4-5-20250929" in cmd


def test_build_command_with_agent_and_files():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command("test", {"agent": "coder", "files": ["main.py", "test.py"]})
    assert "--agent" in cmd
    assert "coder" in cmd
    assert cmd.count("--file") == 2
    assert "main.py" in cmd
    assert "test.py" in cmd


def test_parse_json_output():
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Created the module"}),
        json.dumps({"type": "tool_use", "name": "edit_file", "input": {"path": "main.tf"}}),
        json.dumps({"type": "result", "usage": {"input_tokens": 300, "output_tokens": 120}, "total_cost_usd": 0.005}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost = adapter._parse_output(stdout)
    assert len(conversation) == 2
    assert conversation[0]["content"] == "Created the module"
    assert conversation[1]["tool_use"]["name"] == "edit_file"
    assert token_usage["input"] == 300
    assert token_usage["output"] == 120
    assert cost == 0.005


def test_parse_empty_output():
    adapter = OpenCodeAdapter()
    conversation, token_usage, cost = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None


def test_cli_name():
    adapter = OpenCodeAdapter()
    assert adapter.cli_name() == "opencode"
    assert adapter.agent_type() == "opencode"
