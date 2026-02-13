import json
from agent_eval.adapters.mistral_vibe import MistralVibeAdapter


def test_build_command_minimal():
    adapter = MistralVibeAdapter()
    cmd = adapter._build_command("Write code", {"model": "devstral-2"})
    assert cmd[0] == "vibe"
    assert "-p" in cmd
    assert "--output" in cmd
    assert "json" in cmd
    assert "Write code" in cmd


def test_build_command_with_max_turns():
    adapter = MistralVibeAdapter()
    cmd = adapter._build_command("test", {"model": "devstral-2", "max_turns": 30})
    assert "--max-turns" in cmd
    assert "30" in cmd


def test_generate_config_toml_with_mcp(tmp_path):
    adapter = MistralVibeAdapter()
    adapter._generate_config(tmp_path, {
        "model": "devstral-2",
        "mcp_servers": [
            {"name": "my-server", "transport": "stdio", "command": "npx my-server"},
        ],
    })
    config_file = tmp_path / ".vibe" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "mcp_servers" in content
    assert "devstral-2" in content


def test_parse_json_output():
    adapter = MistralVibeAdapter()
    output = json.dumps([
        {"role": "assistant", "content": "Here is the code"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "abc", "type": "function", "function": {"name": "write_file", "arguments": "{}"}}
        ]},
    ])
    conversation = adapter._parse_output(output)
    assert len(conversation) == 2
    assert conversation[0]["content"] == "Here is the code"
