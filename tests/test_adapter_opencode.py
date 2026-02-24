import json

import pytest

from pitlane.adapters.opencode import OpenCodeAdapter
from pitlane.config import McpServerConfig


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
    cmd = adapter._build_command(
        "test", {"model": "anthropic/claude-sonnet-4-5-20250929"}
    )
    assert "--model" in cmd
    assert "anthropic/claude-sonnet-4-5-20250929" in cmd


def test_build_command_with_agent_and_files():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command(
        "test", {"agent": "coder", "files": ["main.py", "test.py"]}
    )
    assert "--agent" in cmd
    assert "coder" in cmd
    assert cmd.count("--file") == 2
    assert "main.py" in cmd
    assert "test.py" in cmd


def test_parse_json_output():
    """Test parsing basic message types."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Created the module"}),
        json.dumps(
            {
                "type": "tool_use",
                "part": {"tool": "edit_file", "state": {"input": {"path": "main.tf"}}},
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 2
    assert conversation[0]["content"] == "Created the module"
    assert conversation[1]["tool_use"]["name"] == "edit_file"
    assert tool_calls_count == 1


def test_parse_step_finish_tokens():
    """Test parsing tokens from step_finish events (OpenCode format)."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps(
            {
                "type": "tool_use",
                "part": {"tool": "write", "state": {"input": {"path": "hello.py"}}},
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {"input": 12868, "output": 98, "reasoning": 26},
                    "cost": 0,
                },
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {"input": 23, "output": 27, "reasoning": 21},
                    "cost": 0,
                },
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert tool_calls_count == 1
    assert token_usage is not None
    assert token_usage["input"] == 12868 + 23  # Sum of all input tokens
    assert token_usage["output"] == 98 + 27  # Sum of all output tokens
    assert cost is None


def test_parse_empty_output():
    adapter = OpenCodeAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None


def test_get_cli_version_success(mocker):
    """Test getting CLI version when opencode is available."""
    adapter = OpenCodeAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "opencode 1.2.3\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version == "opencode 1.2.3"
    mock_run.assert_called_once_with(
        ["opencode", "--version"], capture_output=True, text=True, timeout=5
    )


def test_get_cli_version_not_found(mocker):
    """Test getting CLI version when opencode is not installed."""
    adapter = OpenCodeAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = FileNotFoundError("opencode not found")

    version = adapter.get_cli_version()

    assert version is None


def test_get_cli_version_error(mocker):
    """Test getting CLI version when command fails."""
    adapter = OpenCodeAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version is None


def test_get_cli_version_empty_output(mocker):
    """Test getting CLI version when output is empty."""
    adapter = OpenCodeAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "   \n  "
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version is None


def test_cli_name():
    adapter = OpenCodeAdapter()
    assert adapter.cli_name() == "opencode"
    assert adapter.agent_type() == "opencode"


def test_build_command_with_session_management():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command(
        "test",
        {
            "session": "abc123",
            "continue": True,
            "fork": True,
        },
    )
    assert "--session" in cmd
    assert "abc123" in cmd
    assert "--continue" in cmd
    assert "--fork" in cmd


def test_build_command_with_session_metadata():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command(
        "test",
        {
            "title": "My Test Session",
            "share": True,
        },
    )
    assert "--title" in cmd
    assert "My Test Session" in cmd
    assert "--share" in cmd


def test_build_command_with_server_attachment():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command(
        "test",
        {
            "attach": "http://localhost:4096",
            "port": 8080,
        },
    )
    assert "--attach" in cmd
    assert "http://localhost:4096" in cmd
    assert "--port" in cmd
    assert "8080" in cmd


def test_build_command_all_options():
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command(
        "Write a function",
        {
            "model": "anthropic/claude-sonnet-4-5-20250929",
            "agent": "coder",
            "files": ["main.py"],
            "session": "test-session",
            "continue": True,
            "title": "Test Task",
            "attach": "http://localhost:4096",
        },
    )
    assert "opencode" in cmd
    assert "run" in cmd
    assert "--format" in cmd
    assert "json" in cmd
    assert "--model" in cmd
    assert "anthropic/claude-sonnet-4-5-20250929" in cmd
    assert "--agent" in cmd
    assert "coder" in cmd
    assert "--file" in cmd
    assert "main.py" in cmd
    assert "--session" in cmd
    assert "test-session" in cmd
    assert "--continue" in cmd
    assert "--title" in cmd
    assert "Test Task" in cmd
    assert "--attach" in cmd
    assert "http://localhost:4096" in cmd
    assert "Write a function" in cmd


def test_opencode_with_custom_model():
    """Test OpenCode adapter with custom model configuration."""
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command(
        "Write a function", {"model": "anthropic/claude-opus-4-20250514"}
    )
    assert "--model" in cmd
    assert "anthropic/claude-opus-4-20250514" in cmd


def test_opencode_with_temperature_settings():
    """Test that temperature settings are passed through config."""
    adapter = OpenCodeAdapter()
    # OpenCode doesn't have explicit temperature flag, but config should be accepted
    cmd = adapter._build_command("test", {"temperature": 0.7})
    # Temperature is not a command-line option in OpenCode, but should not error
    assert "opencode" in cmd
    assert "run" in cmd


def test_opencode_with_max_tokens():
    """Test that max_tokens settings are passed through config."""
    adapter = OpenCodeAdapter()
    # OpenCode doesn't have explicit max_tokens flag, but config should be accepted
    cmd = adapter._build_command("test", {"max_tokens": 4096})
    # max_tokens is not a command-line option in OpenCode, but should not error
    assert "opencode" in cmd
    assert "run" in cmd


def test_opencode_with_thinking_budget():
    """Test that thinking_budget settings are passed through config."""
    adapter = OpenCodeAdapter()
    # OpenCode doesn't have explicit thinking_budget flag, but config should be accepted
    cmd = adapter._build_command("test", {"thinking_budget": 10000})
    # thinking_budget is not a command-line option in OpenCode, but should not error
    assert "opencode" in cmd
    assert "run" in cmd


def test_parse_output_with_empty_lines():
    """Test parsing output with empty lines."""
    adapter = OpenCodeAdapter()
    lines = [
        "",
        json.dumps({"type": "assistant", "content": "Hello"}),
        "",
        json.dumps(
            {"type": "tool_use", "part": {"tool": "edit", "state": {"input": {}}}}
        ),
        "",
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 2
    assert conversation[0]["content"] == "Hello"
    assert tool_calls_count == 1


def test_parse_output_json_decode_error():
    """Test parsing output with invalid JSON lines."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Valid"}),
        "This is not valid JSON",
        "{incomplete json",
        json.dumps(
            {"type": "tool_use", "part": {"tool": "write", "state": {"input": {}}}}
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Should skip invalid JSON and continue parsing
    assert len(conversation) == 2
    assert conversation[0]["content"] == "Valid"
    assert tool_calls_count == 1


def test_parse_output_alternative_message_types():
    """Test parsing output with alternative message type names."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "assistant_message", "content": "Using assistant_message"}),
        json.dumps({"type": "message", "text": "Using message with text field"}),
        json.dumps({"type": "assistant", "content": "Standard assistant"}),
        json.dumps({"type": "text", "part": {"text": "Using text type"}}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 4
    assert conversation[0]["content"] == "Using assistant_message"
    assert conversation[1]["content"] == "Using message with text field"
    assert conversation[2]["content"] == "Standard assistant"
    assert conversation[3]["content"] == "Using text type"


def test_parse_output_step_finish_without_tokens():
    """Test parsing step_finish events without token information."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps(
            {"type": "tool_use", "part": {"tool": "edit", "state": {"input": {}}}}
        ),
        json.dumps({"type": "step_finish", "part": {}}),  # No tokens
        json.dumps({"type": "step_finish", "part": {"cost": 0}}),  # No tokens, has cost
        json.dumps(
            {"type": "step_finish", "part": {"tokens": {}}}
        ),  # Empty tokens dict
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert tool_calls_count == 1
    # Should handle missing tokens gracefully
    assert token_usage is None or token_usage["input"] == 0


def test_parse_output_step_finish_with_cost():
    """Test parsing step_finish events with cost information."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {"input": 100, "output": 50},
                    "cost": 0.005,
                },
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {"input": 200, "output": 100},
                    "cost": 0.010,
                },
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert token_usage["input"] == 300
    assert token_usage["output"] == 150
    assert cost == 0.015


def test_opencode_with_api_error_handling(mocker, tmp_path):
    """Test OpenCode adapter handling API errors."""
    adapter = OpenCodeAdapter()
    logger = mocker.Mock()

    mocker.patch(
        "pitlane.adapters.opencode.run_command_with_live_logging",
        return_value=("", "API Error: Rate limit exceeded", 1, False),
    )

    result = adapter.run("test prompt", tmp_path, {}, logger)

    assert result.exit_code == 1
    assert "Rate limit exceeded" in result.stderr
    assert result.duration_seconds > 0


def test_opencode_with_timeout_error(mocker, tmp_path):
    """Test OpenCode adapter handling timeout errors."""
    adapter = OpenCodeAdapter()
    logger = mocker.Mock()

    mocker.patch(
        "pitlane.adapters.opencode.run_command_with_live_logging",
        side_effect=TimeoutError("Command timed out"),
    )
    result = adapter.run("test prompt", tmp_path, {"timeout": 10}, logger)

    assert result.exit_code == -1
    assert "timed out" in result.stderr.lower()
    assert result.duration_seconds > 0


def test_opencode_with_command_exception(mocker, tmp_path):
    """Test OpenCode adapter handling general command exceptions."""
    adapter = OpenCodeAdapter()
    logger = mocker.Mock()

    mocker.patch(
        "pitlane.adapters.opencode.run_command_with_live_logging",
        side_effect=Exception("Unexpected error"),
    )

    result = adapter.run("test prompt", tmp_path, {}, logger)

    assert result.exit_code == -1
    assert "Unexpected error" in result.stderr
    assert result.duration_seconds > 0
    logger.debug.assert_called()


@pytest.mark.filterwarnings(
    "ignore::RuntimeWarning"
)  # Suppress mock introspection warnings for async functions
def test_parse_output_with_invalid_response_format():
    """Test parsing output with unexpected response formats."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "unknown_type", "data": "something"}),
        json.dumps({"type": "assistant"}),  # Missing content
        json.dumps(
            {"type": "tool_use"}
        ),  # Missing part/tool — should not crash or emit entry
        json.dumps({"no_type_field": "value"}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Should handle gracefully without crashing
    assert isinstance(conversation, list)
    assert isinstance(tool_calls_count, int)


def test_opencode_with_all_options_combined(mocker, tmp_path):
    """Test OpenCode adapter with all configuration options combined."""
    adapter = OpenCodeAdapter()
    logger = mocker.Mock()

    config = {
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "agent": "coder",
        "files": ["main.py", "test.py"],
        "session": "test-session-123",
        "continue": True,
        "fork": True,
        "title": "Complex Test Task",
        "share": True,
        "attach": "http://localhost:4096",
        "port": 8080,
        "timeout": 60,
        "temperature": 0.7,  # Not used by OpenCode but should not error
        "max_tokens": 4096,  # Not used by OpenCode but should not error
    }

    mock_output = json.dumps(
        {
            "type": "step_finish",
            "part": {
                "tokens": {"input": 1000, "output": 500},
                "cost": 0.025,
            },
        }
    )

    mocker.patch(
        "pitlane.adapters.opencode.run_command_with_live_logging",
        return_value=(mock_output, "", 0, False),
    )
    result = adapter.run("Complex test prompt", tmp_path, config, logger)

    # Verify command was built correctly
    cmd = adapter._build_command("Complex test prompt", config)
    assert "--model" in cmd
    assert "anthropic/claude-sonnet-4-5-20250929" in cmd
    assert "--agent" in cmd
    assert "coder" in cmd
    assert "--file" in cmd
    assert "main.py" in cmd
    assert "test.py" in cmd
    assert "--session" in cmd
    assert "test-session-123" in cmd
    assert "--continue" in cmd
    assert "--fork" in cmd
    assert "--title" in cmd
    assert "Complex Test Task" in cmd
    assert "--share" in cmd
    assert "--attach" in cmd
    assert "http://localhost:4096" in cmd
    assert "--port" in cmd
    assert "8080" in cmd

    # Verify result
    assert result.exit_code == 0
    assert result.token_usage is not None
    assert result.token_usage["input"] == 1000
    assert result.token_usage["output"] == 500
    assert result.cost_usd == 0.025


def test_opencode_run_with_debug_logging(mocker, tmp_path):
    """Test that debug logging is called during run."""
    adapter = OpenCodeAdapter()
    logger = mocker.Mock()

    mock_output = json.dumps(
        {
            "type": "step_finish",
            "part": {
                "tokens": {"input": 100, "output": 50},
                "cost": 0.005,
            },
        }
    )

    mocker.patch(
        "pitlane.adapters.opencode.run_command_with_live_logging",
        return_value=(mock_output, "", 0, False),
    )

    adapter.run("test", tmp_path, {"timeout": 30}, logger)

    # Verify debug logging was called
    assert logger.debug.call_count >= 4
    # Check that specific debug messages were logged
    debug_calls = [call[0][0] for call in logger.debug.call_args_list]
    assert any("Command:" in call for call in debug_calls)
    assert any("Working directory:" in call for call in debug_calls)
    assert any("Timeout:" in call for call in debug_calls)
    assert any("Command completed" in call for call in debug_calls)
    assert any("Parsed token_usage:" in call for call in debug_calls)
    assert any("Parsed cost:" in call for call in debug_calls)
    assert any("Parsed tool_calls_count:" in call for call in debug_calls)


def test_parse_output_message_with_empty_content():
    """Test parsing messages with empty content fields."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": ""}),  # Empty content
        json.dumps({"type": "message", "text": ""}),  # Empty text
        json.dumps({"type": "text", "part": {"text": ""}}),  # Empty text type
        json.dumps({"type": "assistant", "content": "Valid content"}),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Should only include messages with non-empty content
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Valid content"


def test_build_command_with_port_as_int():
    """Test that port is correctly converted to string in command."""
    adapter = OpenCodeAdapter()
    cmd = adapter._build_command("test", {"port": 8080})
    assert "--port" in cmd
    port_idx = cmd.index("--port")
    assert cmd[port_idx + 1] == "8080"
    assert isinstance(cmd[port_idx + 1], str)


# ── install_mcp tests ─────────────────────────────────────────────────────────


def test_parse_output_step_finish_cost_without_tokens():
    """Cost must be extracted even when tokens dict is empty or absent."""
    adapter = OpenCodeAdapter()
    lines = [
        json.dumps({"type": "step_finish", "part": {"cost": 0.003}}),
        json.dumps({"type": "step_finish", "part": {"tokens": {}, "cost": 0.002}}),
    ]
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(
        "\n".join(lines)
    )
    assert cost == 0.005
    assert token_usage is None


def test_install_mcp_creates_opencode_json(tmp_path):
    adapter = OpenCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(
        name="oc-server",
        type="stdio",
        command="npx",
        args=["-y", "@org/pkg"],
        env={"TOKEN": "abc"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    target = ws / "opencode.json"
    assert target.exists()
    data = json.loads(target.read_text())
    entry = data["mcp"]["oc-server"]
    assert entry["type"] == "local"
    assert entry["command"] == ["npx", "-y", "@org/pkg"]
    assert entry["environment"] == {"TOKEN": "abc"}
    assert entry["enabled"] is True


def test_install_mcp_merges_existing(tmp_path):
    adapter = OpenCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    existing = {"someOtherKey": True, "mcp": {"old": {"type": "local", "command": []}}}
    (ws / "opencode.json").write_text(json.dumps(existing))

    mcp = McpServerConfig(name="new", command="cmd")
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / "opencode.json").read_text())
    assert data["someOtherKey"] is True
    assert "old" in data["mcp"]
    assert "new" in data["mcp"]
