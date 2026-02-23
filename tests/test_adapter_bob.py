import json
import subprocess

from pitlane.adapters.bob import BobAdapter
from pitlane.config import McpServerConfig


def test_build_command_minimal():
    adapter = BobAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "bob"
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--yolo" in cmd
    assert cmd[-1] == "Write hello world"


def test_build_command_with_chat_mode():
    adapter = BobAdapter()
    cmd = adapter._build_command("test", {"chat_mode": "code"})
    assert "--chat-mode" in cmd
    assert "code" in cmd
    assert cmd[-1] == "test"


def test_build_command_with_max_coins():
    adapter = BobAdapter()
    cmd = adapter._build_command("test", {"max_coins": 100})
    assert "--max-coins" in cmd
    assert "100" in cmd
    assert cmd[-1] == "test"


def _make_result_event(*, input_tokens=200, output_tokens=80, tool_calls=0):
    return json.dumps(
        {
            "type": "result",
            "status": "success",
            "stats": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "duration_ms": 500,
                "tool_calls": tool_calls,
            },
        }
    )


def _make_completion_event(text="Hello from Bob"):
    return json.dumps(
        {
            "type": "tool_use",
            "tool_name": "attempt_completion",
            "tool_id": "tool-1",
            "parameters": {"result": text},
        }
    )


def _make_cost_message(cost=0.09):
    return json.dumps(
        {
            "type": "message",
            "role": "assistant",
            "delta": True,
            "content": f"[using tool attempt_completion: Successfully completed | Cost: {cost}]\n",
        }
    )


def test_parse_json_result():
    adapter = BobAdapter()
    stdout = "\n".join(
        [
            _make_completion_event("Hello from Bob"),
            _make_cost_message(0.09),
            _make_result_event(input_tokens=200, output_tokens=80),
        ]
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Hello from Bob"
    assert token_usage["input"] == 200
    assert token_usage["output"] == 80
    assert cost == 0.09
    assert tool_calls_count == 0


def test_parse_json_with_tool_calls():
    adapter = BobAdapter()
    tool_event = json.dumps(
        {
            "type": "tool_use",
            "tool_name": "bash",
            "tool_id": "tool-2",
            "parameters": {"command": "ls"},
        }
    )
    stdout = "\n".join(
        [
            tool_event,
            tool_event,
            tool_event,
            _make_completion_event("Done"),
            _make_cost_message(0.15),
            _make_result_event(input_tokens=50, output_tokens=20, tool_calls=3),
        ]
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert tool_calls_count == 3
    assert token_usage["input"] == 50
    assert token_usage["output"] == 20
    assert cost == 0.15


def test_parse_json_no_response_text():
    adapter = BobAdapter()
    # Result event only, no attempt_completion
    stdout = _make_result_event(input_tokens=100, output_tokens=40)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert conversation == []
    assert token_usage["input"] == 100
    assert token_usage["output"] == 40
    assert cost is None


def test_parse_non_json_lines_skipped():
    adapter = BobAdapter()
    stdout = "\n".join(
        [
            "YOLO mode is enabled. All tool calls will be automatically approved.",
            "---output---",
            _make_completion_event("Hello from Bob"),
            "---output---",
            _make_result_event(input_tokens=10, output_tokens=5),
        ]
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Hello from Bob"
    assert token_usage["input"] == 10
    assert token_usage["output"] == 5


def test_parse_no_result_event():
    adapter = BobAdapter()
    # attempt_completion only, no result event
    stdout = _make_completion_event("Hello from Bob")
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Hello from Bob"
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


def test_parse_cost_extracted_from_message():
    adapter = BobAdapter()
    stdout = "\n".join(
        [
            _make_completion_event("Done"),
            _make_cost_message(0.42),
            _make_result_event(input_tokens=100, output_tokens=50),
        ]
    )
    _, _, cost, _ = adapter._parse_output(stdout)
    assert cost == 0.42


def test_parse_non_cost_message_does_not_set_cost():
    adapter = BobAdapter()
    non_cost_message = json.dumps(
        {
            "type": "message",
            "role": "assistant",
            "delta": True,
            "content": "[using tool write_to_file: Writing to fib.py]\n",
        }
    )
    stdout = "\n".join(
        [
            non_cost_message,
            _make_completion_event("Done"),
            _make_result_event(input_tokens=10, output_tokens=5),
        ]
    )
    _, _, cost, _ = adapter._parse_output(stdout)
    assert cost is None


def test_bob_with_custom_model():
    """Test bob adapter with custom model configuration."""
    adapter = BobAdapter()
    config = {"model": "claude-3-5-sonnet-20241022"}
    cmd = adapter._build_command("test prompt", config)
    assert cmd[0] == "bob"
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--yolo" in cmd
    assert cmd[-1] == "test prompt"


def test_bob_with_api_error_handling(tmp_path, monkeypatch):
    """Test bob adapter handles API errors gracefully."""
    import logging

    adapter = BobAdapter()
    logger = logging.getLogger("test")

    def mock_run_command(*args, **kwargs):
        raise Exception("API Error: Rate limit exceeded")

    monkeypatch.setattr(
        "pitlane.adapters.bob.run_command_with_live_logging", mock_run_command
    )

    result = adapter.run("test", tmp_path, {}, logger)
    assert result.exit_code == -1
    assert "API Error" in result.stderr
    assert result.conversation == []
    assert result.token_usage is None
    assert result.cost_usd is None


def test_bob_with_timeout_error(tmp_path, monkeypatch):
    """Test bob adapter handles timeout errors."""
    import logging

    adapter = BobAdapter()
    logger = logging.getLogger("test")

    def mock_run_command(*args, **kwargs):
        raise TimeoutError("Command timed out")

    monkeypatch.setattr(
        "pitlane.adapters.bob.run_command_with_live_logging", mock_run_command
    )

    result = adapter.run("test", tmp_path, {"timeout": 10}, logger)
    assert result.exit_code == -1
    assert "timed out" in result.stderr.lower()
    assert result.duration_seconds > 0


def test_bob_with_invalid_response_format():
    """Test bob adapter handles invalid JSON response format."""
    adapter = BobAdapter()
    # Mix of invalid JSON and valid events
    stdout = "\n".join(
        [
            "Invalid JSON line",
            '{"type": "invalid_type", "data": "something"}',
            _make_completion_event("Valid response"),
            "Another non-JSON line",
            _make_result_event(input_tokens=50, output_tokens=25),
        ]
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Should still parse valid events
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Valid response"
    assert token_usage["input"] == 50
    assert token_usage["output"] == 25


def test_bob_with_empty_response():
    """Test bob adapter handles empty or whitespace-only response."""
    adapter = BobAdapter()
    # Empty completion result
    empty_completion = json.dumps(
        {
            "type": "tool_use",
            "tool_name": "attempt_completion",
            "tool_id": "tool-1",
            "parameters": {"result": ""},
        }
    )
    stdout = "\n".join(
        [
            empty_completion,
            _make_result_event(input_tokens=10, output_tokens=5),
        ]
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    # Empty result should not be added to conversation
    assert len(conversation) == 0
    assert token_usage["input"] == 10
    assert token_usage["output"] == 5


def test_bob_with_all_options_combined():
    """Test bob adapter with all configuration options combined."""
    adapter = BobAdapter()
    config = {
        "chat_mode": "code",
        "max_coins": 500,
        "timeout": 600,
        "model": "claude-3-5-sonnet-20241022",
    }
    cmd = adapter._build_command("complex task", config)
    assert cmd[0] == "bob"
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--yolo" in cmd
    assert "--chat-mode" in cmd
    assert "code" in cmd
    assert "--max-coins" in cmd
    assert "500" in cmd
    assert cmd[-1] == "complex task"


def test_bob_cli_name():
    """Test bob adapter returns correct CLI name."""
    adapter = BobAdapter()
    assert adapter.cli_name() == "bob"


def test_bob_agent_type():
    """Test bob adapter returns correct agent type."""
    adapter = BobAdapter()
    assert adapter.agent_type() == "bob"


def test_bob_get_cli_version_success(mocker, monkeypatch):
    """Test bob adapter gets CLI version successfully."""
    adapter = BobAdapter()

    def mock_run(*args, **kwargs):
        result = mocker.Mock()
        result.returncode = 0
        result.stdout = "bob version 1.0.0\n"
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)
    version = adapter.get_cli_version()
    assert version == "bob version 1.0.0"


def test_bob_get_cli_version_failure(monkeypatch):
    """Test bob adapter handles CLI version check failure."""
    adapter = BobAdapter()

    def mock_run(*args, **kwargs):
        raise Exception("Command not found")

    monkeypatch.setattr(subprocess, "run", mock_run)
    version = adapter.get_cli_version()
    assert version is None


def test_bob_run_with_debug_logging(tmp_path, monkeypatch):
    """Test bob adapter logs debug information during run."""
    import logging

    adapter = BobAdapter()
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
        "pitlane.adapters.bob.run_command_with_live_logging", mock_run_command
    )

    result = adapter.run("test prompt", tmp_path, {"timeout": 60}, logger)

    # Verify debug logging occurred
    assert any("Command:" in msg for msg in log_messages)
    assert any("Working directory:" in msg for msg in log_messages)
    assert any("Timeout:" in msg for msg in log_messages)
    assert any("Config:" in msg for msg in log_messages)
    assert any("Command completed" in msg for msg in log_messages)
    assert result.exit_code == 0


# ── install_mcp tests ─────────────────────────────────────────────────────────


def test_install_mcp_creates_bob_mcp_json(tmp_path):
    adapter = BobAdapter()
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

    target = ws / ".bob" / "mcp.json"
    assert target.exists()
    data = json.loads(target.read_text())
    assert "mcpServers" in data
    entry = data["mcpServers"]["my-server"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "@org/pkg"]
    assert entry["env"] == {"KEY": "val"}


def test_install_mcp_merges_existing(tmp_path):
    adapter = BobAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    bob_dir = ws / ".bob"
    bob_dir.mkdir()
    existing = {"mcpServers": {"old-server": {"type": "stdio", "command": "old-cmd"}}}
    (bob_dir / "mcp.json").write_text(json.dumps(existing))

    mcp = McpServerConfig(name="new-server", type="stdio", command="new-cmd")
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((bob_dir / "mcp.json").read_text())
    assert "old-server" in data["mcpServers"]
    assert "new-server" in data["mcpServers"]


def test_install_mcp_creates_bob_dir(tmp_path):
    adapter = BobAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(name="server", type="stdio", command="cmd")
    adapter.install_mcp(workspace=ws, mcp=mcp)

    assert (ws / ".bob").is_dir()
    assert (ws / ".bob" / "mcp.json").exists()
