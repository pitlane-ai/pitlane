import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from agent_eval.adapters.claude_code import ClaudeCodeAdapter


def test_build_command_minimal():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command("Write hello world", {"model": "sonnet"})
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--model" in cmd
    assert "sonnet" in cmd
    assert cmd[-1] == "Write hello world"


def test_build_command_with_mcp():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command("test", {"model": "sonnet", "mcp_config": "./mcp.json"})
    assert "--mcp-config" in cmd
    assert "./mcp.json" in cmd


def test_build_command_with_system_prompt():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command("test", {"model": "sonnet", "system_prompt": "Be helpful"})
    assert "--append-system-prompt" in cmd
    assert "Be helpful" in cmd


def test_parse_stream_json_result():
    adapter = ClaudeCodeAdapter()
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "abc"}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}),
        json.dumps({
            "type": "result", "subtype": "success",
            "duration_ms": 1500, "total_cost_usd": 0.02,
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "result": "Done",
        }),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost = adapter._parse_output(stdout)
    assert len(conversation) >= 1
    assert token_usage["input"] == 100
    assert token_usage["output"] == 50
    assert cost == 0.02
