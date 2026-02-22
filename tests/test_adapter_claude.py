import json
import subprocess
from pathlib import Path

import pytest

from pitlane.adapters.claude_code import ClaudeCodeAdapter
from pitlane.config import McpServerConfig


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
    cmd = adapter._build_command(
        "test", {"model": "sonnet", "mcp_config": "./mcp.json"}
    )
    assert "--mcp-config" in cmd
    assert "./mcp.json" in cmd


def test_build_command_with_system_prompt():
    adapter = ClaudeCodeAdapter()
    cmd = adapter._build_command(
        "test", {"model": "sonnet", "system_prompt": "Be helpful"}
    )
    assert "--append-system-prompt" in cmd
    assert "Be helpful" in cmd


def test_parse_stream_json_result():
    adapter = ClaudeCodeAdapter()
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "abc"}),
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello"}]},
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 1500,
                "total_cost_usd": 0.02,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "result": "Done",
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) >= 1
    assert token_usage["input"] == 100
    assert token_usage["output"] == 50
    assert cost == 0.02
    assert tool_calls_count == 0


def test_claude_with_custom_model():
    """Test claude adapter with custom model configuration."""
    adapter = ClaudeCodeAdapter()
    config = {"model": "claude-3-5-sonnet-20241022"}
    cmd = adapter._build_command("test prompt", config)
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--model" in cmd
    assert "claude-3-5-sonnet-20241022" in cmd
    assert cmd[-1] == "test prompt"


def test_claude_with_api_error_handling(tmp_path, monkeypatch):
    """Test claude adapter handles API errors gracefully."""
    import logging

    adapter = ClaudeCodeAdapter()
    logger = logging.getLogger("test")

    def mock_run_command(*args, **kwargs):
        raise Exception("API Error: Authentication failed")

    monkeypatch.setattr(
        "pitlane.adapters.claude_code.run_streaming_sync", mock_run_command
    )

    result = adapter.run("test", tmp_path, {"model": "sonnet"}, logger)
    assert result.exit_code == -1
    assert "API Error" in result.stderr
    assert result.conversation == []
    assert result.token_usage is None
    assert result.cost_usd is None


def test_claude_with_timeout_error(tmp_path, monkeypatch):
    """Test claude adapter handles timeout errors."""
    import logging

    adapter = ClaudeCodeAdapter()
    logger = logging.getLogger("test")

    def mock_run_command(*args, **kwargs):
        raise TimeoutError("Command execution timed out")

    monkeypatch.setattr(
        "pitlane.adapters.claude_code.run_streaming_sync", mock_run_command
    )

    result = adapter.run("test", tmp_path, {"model": "sonnet", "timeout": 30}, logger)
    assert result.exit_code == -1
    assert "timed out" in result.stderr.lower()
    assert result.duration_seconds > 0


def test_claude_with_invalid_response_format():
    """Test claude adapter handles invalid JSON response format."""
    adapter = ClaudeCodeAdapter()
    # Mix of invalid JSON and valid events
    lines = [
        "Invalid JSON line",
        '{"type": "unknown", "data": "something"}',
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Valid response"}]},
            }
        ),
        "Another non-JSON line",
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 1000,
                "total_cost_usd": 0.01,
                "usage": {"input_tokens": 30, "output_tokens": 15},
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Should still parse valid events
    assert len(conversation) >= 1
    assert token_usage["input"] == 30
    assert token_usage["output"] == 15
    assert cost == 0.01


def test_claude_with_empty_response():
    """Test claude adapter handles empty or whitespace-only response."""
    adapter = ClaudeCodeAdapter()
    # Response with empty lines and minimal content
    lines = [
        "",
        "   ",
        json.dumps({"type": "system", "subtype": "init", "session_id": "test"}),
        "",
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 500,
                "total_cost_usd": 0.005,
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Should handle empty lines gracefully
    assert token_usage["input"] == 5
    assert token_usage["output"] == 2
    assert cost == 0.005


def test_claude_with_all_options_combined():
    """Test claude adapter with all configuration options combined."""
    adapter = ClaudeCodeAdapter()
    config = {
        "model": "claude-3-5-sonnet-20241022",
        "mcp_config": "./config/mcp.json",
        "system_prompt": "You are a helpful coding assistant",
        "max_turns": 10,
        "max_budget_usd": 1.0,
        "timeout": 600,
    }
    cmd = adapter._build_command("complex task", config)
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--model" in cmd
    assert "claude-3-5-sonnet-20241022" in cmd
    assert "--mcp-config" in cmd
    assert "./config/mcp.json" in cmd
    assert "--append-system-prompt" in cmd
    assert "You are a helpful coding assistant" in cmd
    assert "--max-turns" in cmd
    assert "10" in cmd
    assert "--max-budget-usd" in cmd
    assert "1.0" in cmd
    assert cmd[-1] == "complex task"


def test_claude_cli_name():
    """Test claude adapter returns correct CLI name."""
    adapter = ClaudeCodeAdapter()
    assert adapter.cli_name() == "claude"


def test_claude_agent_type():
    """Test claude adapter returns correct agent type."""
    adapter = ClaudeCodeAdapter()
    assert adapter.agent_type() == "claude-code"


def test_claude_get_cli_version_success(mocker, monkeypatch):
    """Test claude adapter gets CLI version successfully."""
    adapter = ClaudeCodeAdapter()

    def mock_run(*args, **kwargs):
        result = mocker.Mock()
        result.returncode = 0
        result.stdout = "claude version 2.0.0\n"
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)
    version = adapter.get_cli_version()
    assert version == "claude version 2.0.0"


def test_claude_get_cli_version_failure(monkeypatch):
    """Test claude adapter handles CLI version check failure."""
    adapter = ClaudeCodeAdapter()

    def mock_run(*args, **kwargs):
        raise Exception("Command not found")

    monkeypatch.setattr(subprocess, "run", mock_run)
    version = adapter.get_cli_version()
    assert version is None


def test_claude_parse_output_with_tool_use():
    """Test claude adapter parses tool_use blocks correctly."""
    adapter = ClaudeCodeAdapter()
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "write_file",
                            "input": {"path": "test.py", "content": "print('hello')"},
                        }
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 1000,
                "total_cost_usd": 0.01,
                "usage": {"input_tokens": 20, "output_tokens": 10},
            }
        ),
    ]
    stdout = "\n".join(lines)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert tool_calls_count == 1
    assert len(conversation) == 1
    assert conversation[0]["role"] == "assistant"
    assert "tool_use" in conversation[0]


def test_claude_run_with_debug_logging(tmp_path, monkeypatch):
    """Test claude adapter logs debug information during run."""
    import logging

    adapter = ClaudeCodeAdapter()
    logger = logging.getLogger("test")
    logger.setLevel(logging.DEBUG)

    # Capture log messages
    log_messages = []
    original_debug = logger.debug

    def capture_debug(msg):
        log_messages.append(msg)
        original_debug(msg)

    logger.debug = capture_debug

    def mock_run_command(*args, **kwargs):
        return "test output", "", 0, False

    monkeypatch.setattr(
        "pitlane.adapters.claude_code.run_streaming_sync", mock_run_command
    )

    result = adapter.run(
        "test prompt", tmp_path, {"model": "sonnet", "timeout": 60}, logger
    )

    # Verify debug logging occurred
    assert any("Command:" in msg for msg in log_messages)
    assert any("Working directory:" in msg for msg in log_messages)
    assert any("Timeout:" in msg for msg in log_messages)
    assert any("Config:" in msg for msg in log_messages)
    assert any("Command completed" in msg for msg in log_messages)
    assert result.exit_code == 0


# ── install_mcp tests ─────────────────────────────────────────────────────────


def test_install_mcp_creates_mcp_json(tmp_path: Path):
    adapter = ClaudeCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(
        name="my-server",
        type="stdio",
        command="npx",
        args=["-y", "@org/pkg"],
        env={"KEY": "val"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    target = ws / ".mcp.json"
    assert target.exists()
    data = json.loads(target.read_text())
    assert "mcpServers" in data
    entry = data["mcpServers"]["my-server"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "@org/pkg"]
    assert entry["env"] == {"KEY": "val"}


def test_install_mcp_merges_existing(tmp_path: Path):
    adapter = ClaudeCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    existing = {"mcpServers": {"old-server": {"type": "stdio", "command": "old-cmd"}}}
    (ws / ".mcp.json").write_text(json.dumps(existing))

    mcp = McpServerConfig(name="new-server", type="stdio", command="new-cmd")
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / ".mcp.json").read_text())
    assert "old-server" in data["mcpServers"]
    assert "new-server" in data["mcpServers"]


def test_install_mcp_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter = ClaudeCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("TEST_SECRET", "my-secret-value")

    mcp = McpServerConfig(
        name="env-server",
        command="cmd",
        env={"SECRET": "${TEST_SECRET}", "STATIC": "literal"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / ".mcp.json").read_text())
    entry_env = data["mcpServers"]["env-server"]["env"]
    assert entry_env["SECRET"] == "my-secret-value"
    assert entry_env["STATIC"] == "literal"


def test_install_mcp_env_expansion_with_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    adapter = ClaudeCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.delenv("UNSET_VAR", raising=False)

    mcp = McpServerConfig(
        name="default-server",
        command="cmd",
        env={"VAR": "${UNSET_VAR:-fallback-value}"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / ".mcp.json").read_text())
    entry_env = data["mcpServers"]["default-server"]["env"]
    assert entry_env["VAR"] == "fallback-value"


def test_install_mcp_env_missing_var_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    adapter = ClaudeCodeAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.delenv("TOTALLY_MISSING", raising=False)

    mcp = McpServerConfig(
        name="bad-server",
        command="cmd",
        env={"KEY": "${TOTALLY_MISSING}"},
    )
    with pytest.raises(Exception, match="TOTALLY_MISSING"):
        adapter.install_mcp(workspace=ws, mcp=mcp)
