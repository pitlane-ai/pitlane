import json
from agent_eval.adapters.codex import CodexAdapter


def test_build_command_minimal():
    adapter = CodexAdapter()
    cmd = adapter._build_command("Write code", {"model": "o3"})
    assert cmd[0] == "codex"
    assert "exec" in cmd
    assert "--json" in cmd
    assert "-m" in cmd
    assert "o3" in cmd


def test_build_command_with_sandbox():
    adapter = CodexAdapter()
    cmd = adapter._build_command("test", {"model": "o3", "sandbox": "danger-full-access"})
    assert "-s" in cmd
    assert "danger-full-access" in cmd


def test_generate_config_toml_with_mcp(tmp_path):
    adapter = CodexAdapter()
    adapter._generate_config(tmp_path, {
        "mcp_servers": {
            "my-server": {"command": "npx", "args": ["-y", "my-mcp-server"]},
        }
    })
    config_file = tmp_path / ".codex" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "mcp_servers" in content
    assert "my-server" in content


def test_parse_jsonl_output():
    adapter = CodexAdapter()
    lines = [
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 200, "output_tokens": 80, "cached_input_tokens": 10}}),
        json.dumps({"type": "agent_message", "content": "Done writing code"}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert token_usage["input"] == 200
    assert token_usage["output"] == 80
    assert cost is None  # Codex doesn't report cost directly
    assert tool_calls_count == 0
