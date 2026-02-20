import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest
from pitlane.adapters.mistral_vibe import MistralVibeAdapter


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    logger = Mock(spec=logging.Logger)
    logger.debug = Mock()
    return logger


@pytest.fixture
def adapter():
    """Create a MistralVibeAdapter instance."""
    return MistralVibeAdapter()


# ============================================================================
# Command Building Tests
# ============================================================================


def test_build_command_minimal(adapter):
    cmd = adapter._build_command("Write code", {"model": "devstral-2"})
    assert cmd[0] == "vibe"
    assert "-p" in cmd
    assert "--output" in cmd
    assert "json" in cmd
    assert "Write code" in cmd


def test_build_command_with_max_turns(adapter):
    cmd = adapter._build_command("test", {"model": "devstral-2", "max_turns": 30})
    assert "--max-turns" in cmd
    assert "30" in cmd


def test_build_command_with_max_price(adapter):
    """Test command building with max_price option."""
    cmd = adapter._build_command("test", {"max_price": 0.50})
    assert "--max-price" in cmd
    assert "0.5" in cmd


def test_build_command_with_all_options(adapter):
    """Test command building with all available options."""
    cmd = adapter._build_command("test prompt", {"max_turns": 20, "max_price": 1.0})
    assert "vibe" in cmd
    assert "-p" in cmd
    assert "test prompt" in cmd
    assert "--output" in cmd
    assert "json" in cmd
    assert "--max-turns" in cmd
    assert "20" in cmd
    assert "--max-price" in cmd
    assert "1.0" in cmd


# ============================================================================
# Config Generation Tests
# ============================================================================


def test_generate_config_with_model_only(tmp_path, adapter):
    """Test config generation with only model specified."""
    adapter._generate_config(tmp_path, {"model": "devstral-2"})
    config_file = tmp_path / ".vibe" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert 'active_model = "devstral-2"' in content


def test_generate_config_toml_with_mcp(tmp_path, adapter):
    adapter._generate_config(
        tmp_path,
        {
            "model": "devstral-2",
            "mcp_servers": [
                {"name": "my-server", "transport": "stdio", "command": "npx my-server"},
            ],
        },
    )
    config_file = tmp_path / ".vibe" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "mcp_servers" in content
    assert "devstral-2" in content


def test_generate_config_with_complex_mcp_values(tmp_path, adapter):
    """Test config generation with complex MCP server configurations."""
    adapter._generate_config(
        tmp_path,
        {
            "model": "codestral-latest",
            "mcp_servers": [
                {
                    "name": "server1",
                    "transport": "stdio",
                    "command": "node server.js",
                    "port": 8080,
                },
                {
                    "name": "server2",
                    "transport": "http",
                    "url": "http://localhost:3000",
                },
            ],
        },
    )
    config_file = tmp_path / ".vibe" / "config.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "server1" in content
    assert "server2" in content
    assert "port = 8080" in content
    assert '"http://localhost:3000"' in content


def test_generate_config_empty_config(tmp_path, adapter):
    """Test that empty config doesn't create config file."""
    adapter._generate_config(tmp_path, {})
    config_file = tmp_path / ".vibe" / "config.toml"
    assert not config_file.exists()


# ============================================================================
# Output Parsing Tests
# ============================================================================


def test_parse_json_output(adapter):
    output = json.dumps(
        [
            {"role": "assistant", "content": "Here is the code"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "abc",
                        "type": "function",
                        "function": {"name": "write_file", "arguments": "{}"},
                    }
                ],
            },
        ]
    )
    conversation = adapter._parse_output(output)
    assert len(conversation) == 2
    assert conversation[0]["content"] == "Here is the code"


def test_parse_output_invalid_json(adapter):
    """Test parsing with invalid JSON returns empty conversation."""
    output = "not valid json {["
    conversation = adapter._parse_output(output)
    assert conversation == []


def test_parse_output_non_dict_items(adapter):
    """Test parsing skips non-dict items in list."""
    output = json.dumps(
        [
            {"role": "assistant", "content": "valid"},
            "invalid string item",
            123,
            {"role": "assistant", "content": "also valid"},
        ]
    )
    conversation = adapter._parse_output(output)
    assert len(conversation) == 2
    assert conversation[0]["content"] == "valid"
    assert conversation[1]["content"] == "also valid"


def test_parse_output_tool_calls_with_text(adapter):
    """Test parsing tool calls that also have text content."""
    output = json.dumps(
        [
            {
                "role": "assistant",
                "content": "I'll write the file now",
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path": "test.py", "content": "print()"}',
                        },
                    }
                ],
            }
        ]
    )
    conversation = adapter._parse_output(output)
    # Should have 2 entries: one for text, one for tool call
    assert len(conversation) == 2
    assert conversation[0]["content"] == "I'll write the file now"
    assert conversation[1]["tool_use"]["name"] == "write_file"


def test_parse_output_tool_args_json_error(adapter):
    """Test parsing handles JSON decode errors in tool arguments."""
    output = json.dumps(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "execute", "arguments": "invalid json {["},
                    }
                ],
            }
        ]
    )
    conversation = adapter._parse_output(output)
    assert len(conversation) == 1
    assert conversation[0]["tool_use"]["input"] == {"raw": "invalid json {["}


def test_parse_output_assistant_without_tools(adapter):
    """Test parsing assistant messages without tool calls."""
    output = json.dumps(
        [
            {"role": "assistant", "content": "Simple response"},
            {"role": "assistant", "content": "Another response"},
        ]
    )
    conversation = adapter._parse_output(output)
    assert len(conversation) == 2
    assert all(msg["role"] == "assistant" for msg in conversation)
    assert conversation[0]["content"] == "Simple response"


def test_parse_output_empty_content(adapter):
    """Test parsing handles empty content fields."""
    output = json.dumps(
        [
            {"role": "assistant", "content": ""},
            {"role": "assistant"},  # Missing content
        ]
    )
    conversation = adapter._parse_output(output)
    assert len(conversation) == 2
    assert conversation[0]["content"] == ""
    assert conversation[1]["content"] == ""


def test_parse_output_single_dict(adapter):
    """Test parsing handles single dict instead of list."""
    output = json.dumps({"role": "assistant", "content": "Single message"})
    conversation = adapter._parse_output(output)
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Single message"


def test_parse_output_multiple_tool_calls(adapter):
    """Test parsing multiple tool calls in one message."""
    output = json.dumps(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call1",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "a.txt"}',
                        },
                    },
                    {
                        "id": "call2",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path": "b.txt"}',
                        },
                    },
                ],
            }
        ]
    )
    conversation = adapter._parse_output(output)
    assert len(conversation) == 2
    assert conversation[0]["tool_use"]["name"] == "read_file"
    assert conversation[1]["tool_use"]["name"] == "write_file"


# ============================================================================
# Session Stats Reading Tests
# ============================================================================


def test_read_session_stats_no_directory(adapter, mock_logger, tmp_path):
    """Test reading stats when session directory doesn't exist."""
    vibe_home = str(tmp_path / "nonexistent")
    token_usage, cost, tool_calls = adapter._read_session_stats(vibe_home, mock_logger)
    assert token_usage is None
    assert cost is None
    assert tool_calls == 0
    mock_logger.debug.assert_called_with("No vibe session log directory found")


def test_read_session_stats_no_meta_files(adapter, mock_logger, tmp_path):
    """Test reading stats when no meta.json files exist."""
    vibe_home = tmp_path / "vibe_home"
    session_dir = vibe_home / "logs" / "session"
    session_dir.mkdir(parents=True)

    token_usage, cost, tool_calls = adapter._read_session_stats(
        str(vibe_home), mock_logger
    )
    assert token_usage is None
    assert cost is None
    assert tool_calls == 0
    mock_logger.debug.assert_called_with("No vibe session meta.json found")


def test_read_session_stats_invalid_json(adapter, mock_logger, tmp_path):
    """Test reading stats with invalid JSON in meta file."""
    vibe_home = tmp_path / "vibe_home"
    session_dir = vibe_home / "logs" / "session" / "session_001"
    session_dir.mkdir(parents=True)
    meta_file = session_dir / "meta.json"
    meta_file.write_text("invalid json {[")

    token_usage, cost, tool_calls = adapter._read_session_stats(
        str(vibe_home), mock_logger
    )
    assert token_usage is None
    assert cost is None
    assert tool_calls == 0


def test_read_session_stats_missing_stats(adapter, mock_logger, tmp_path):
    """Test reading stats when stats field is missing."""
    vibe_home = tmp_path / "vibe_home"
    session_dir = vibe_home / "logs" / "session" / "session_001"
    session_dir.mkdir(parents=True)
    meta_file = session_dir / "meta.json"
    meta_file.write_text(json.dumps({"other_field": "value"}))

    token_usage, cost, tool_calls = adapter._read_session_stats(
        str(vibe_home), mock_logger
    )
    assert token_usage is None
    assert cost is None
    assert tool_calls == 0


def test_read_session_stats_success(adapter, mock_logger, tmp_path):
    """Test successful reading of session stats."""
    vibe_home = tmp_path / "vibe_home"
    session_dir = vibe_home / "logs" / "session" / "session_001"
    session_dir.mkdir(parents=True)
    meta_file = session_dir / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "stats": {
                    "session_prompt_tokens": 100,
                    "session_completion_tokens": 50,
                    "session_cost": 0.025,
                    "tool_calls_agreed": 5,
                }
            }
        )
    )

    token_usage, cost, tool_calls = adapter._read_session_stats(
        str(vibe_home), mock_logger
    )
    assert token_usage == {"input": 100, "output": 50}
    assert cost == 0.025
    assert tool_calls == 5


def test_read_session_stats_multiple_sessions(adapter, mock_logger, tmp_path):
    """Test reading stats picks the most recent session."""
    vibe_home = tmp_path / "vibe_home"
    session_dir = vibe_home / "logs" / "session"

    # Create older session
    old_session = session_dir / "session_001"
    old_session.mkdir(parents=True)
    (old_session / "meta.json").write_text(
        json.dumps(
            {"stats": {"session_prompt_tokens": 10, "session_completion_tokens": 5}}
        )
    )

    # Create newer session
    new_session = session_dir / "session_002"
    new_session.mkdir(parents=True)
    (new_session / "meta.json").write_text(
        json.dumps(
            {"stats": {"session_prompt_tokens": 100, "session_completion_tokens": 50}}
        )
    )

    token_usage, cost, tool_calls = adapter._read_session_stats(
        str(vibe_home), mock_logger
    )
    assert token_usage == {"input": 100, "output": 50}


def test_read_session_stats_zero_tokens(adapter, mock_logger, tmp_path):
    """Test reading stats with zero tokens returns None for token_usage."""
    vibe_home = tmp_path / "vibe_home"
    session_dir = vibe_home / "logs" / "session" / "session_001"
    session_dir.mkdir(parents=True)
    meta_file = session_dir / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "stats": {
                    "session_prompt_tokens": 0,
                    "session_completion_tokens": 0,
                    "session_cost": 0.0,
                }
            }
        )
    )

    token_usage, cost, tool_calls = adapter._read_session_stats(
        str(vibe_home), mock_logger
    )
    assert token_usage is None  # Both tokens are 0
    assert cost == 0.0


# ============================================================================
# Run Method Tests
# ============================================================================


def test_run_missing_env_file(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run method when .env file is missing."""
    # Create a fake home directory without .env
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()

    # Mock Path.home() to return our fake home
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with pytest.raises(RuntimeError, match="No ~/.vibe/.env found"):
        adapter.run("test prompt", tmp_path, {}, mock_logger)


def test_run_command_exception(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run method handles command execution exceptions."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Mock run_command_with_streaming to raise exception
    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.side_effect = Exception("Command failed")

        result = adapter.run("test prompt", tmp_path, {}, mock_logger)
        assert result.exit_code == -1
        assert "Command failed" in result.stderr
        assert result.duration_seconds > 0


@pytest.mark.filterwarnings(
    "ignore::RuntimeWarning"
)  # Suppress mock introspection warnings for async functions
def test_run_with_timeout(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run method with custom timeout."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Mock successful command execution
    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.return_value = ("output", "", 0)

        adapter.run("test", tmp_path, {"timeout": 600}, mock_logger)

        # Verify timeout was logged
        debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
        assert any("600s" in call for call in debug_calls)


def test_run_success_with_session_stats(adapter, mock_logger, tmp_path, monkeypatch):
    """Test successful run with session stats."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Mock tempfile.mkdtemp to return a known location
    vibe_home = tmp_path / "vibe_home"
    vibe_home.mkdir()
    monkeypatch.setattr(
        "pitlane.adapters.mistral_vibe.tempfile.mkdtemp", lambda prefix: str(vibe_home)
    )

    # Create session stats
    session_dir = vibe_home / "logs" / "session" / "session_001"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps(
            {
                "stats": {
                    "session_prompt_tokens": 150,
                    "session_completion_tokens": 75,
                    "session_cost": 0.05,
                    "tool_calls_agreed": 3,
                }
            }
        )
    )

    # Mock successful command with JSON output
    output = json.dumps([{"role": "assistant", "content": "Done"}])
    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.return_value = (output, "", 0)

        result = adapter.run("test", tmp_path, {}, mock_logger)
        assert result.exit_code == 0
        assert result.token_usage == {"input": 150, "output": 75}
        assert result.cost_usd == 0.05
        assert result.tool_calls_count == 3
        assert len(result.conversation) == 1


@pytest.mark.filterwarnings(
    "ignore::RuntimeWarning"
)  # Suppress mock introspection warnings for async functions
def test_run_with_custom_model(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run with custom model configuration."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.return_value = ("[]", "", 0)

        adapter.run("test", tmp_path, {"model": "codestral-latest"}, mock_logger)

        # Verify config was generated
        config_file = tmp_path / ".vibe" / "config.toml"
        assert config_file.exists()
        assert "codestral-latest" in config_file.read_text()


def test_run_with_empty_response(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run with empty response."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.return_value = ("", "", 0)

        result = adapter.run("test", tmp_path, {}, mock_logger)
        assert result.exit_code == 0
        assert result.conversation == []


@pytest.mark.filterwarnings(
    "ignore::RuntimeWarning"
)  # Suppress mock introspection warnings for async functions
def test_run_with_invalid_response_format(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run with invalid JSON response format."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.return_value = ("invalid json {[", "", 0)

        result = adapter.run("test", tmp_path, {}, mock_logger)
        assert result.exit_code == 0
        assert result.conversation == []  # Invalid JSON returns empty conversation


def test_run_with_all_options_combined(adapter, mock_logger, tmp_path, monkeypatch):
    """Test run with all configuration options combined."""
    # Setup fake home with .env
    fake_home = tmp_path / "fake_home"
    vibe_dir = fake_home / ".vibe"
    vibe_dir.mkdir(parents=True)
    (vibe_dir / ".env").write_text("API_KEY=test")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with patch(
        "pitlane.adapters.mistral_vibe.run_command_with_streaming",
        new_callable=AsyncMock,
    ) as mock_streaming:
        mock_streaming.return_value = ("[]", "", 0)

        config = {
            "model": "codestral-latest",
            "max_turns": 25,
            "max_price": 2.0,
            "timeout": 600,
            "mcp_servers": [{"name": "test-server", "command": "node server.js"}],
        }

        result = adapter.run("complex test", tmp_path, config, mock_logger)
        assert result.exit_code == 0

        # Verify config file has all settings
        config_file = tmp_path / ".vibe" / "config.toml"
        content = config_file.read_text()
        assert "codestral-latest" in content
        assert "test-server" in content


# ============================================================================
# Adapter Metadata Tests
# ============================================================================


def test_cli_name(adapter):
    """Test CLI name is correct."""
    assert adapter.cli_name() == "vibe"


def test_agent_type(adapter):
    """Test agent type is correct."""
    assert adapter.agent_type() == "mistral-vibe"


@pytest.mark.filterwarnings(
    "ignore::RuntimeWarning"
)  # Suppress mock introspection warnings for async functions
@patch("subprocess.run")
def test_get_cli_version_success(mock_run, adapter):
    """Test getting CLI version successfully."""
    mock_run.return_value = Mock(returncode=0, stdout="vibe 1.0.0\n")
    version = adapter.get_cli_version()
    assert version == "vibe 1.0.0"


@patch("subprocess.run")
def test_get_cli_version_failure(mock_run, adapter):
    """Test getting CLI version when command fails."""
    mock_run.return_value = Mock(returncode=1, stdout="")
    version = adapter.get_cli_version()
    assert version is None


@patch("subprocess.run")
def test_get_cli_version_exception(mock_run, adapter):
    """Test getting CLI version when exception occurs."""
    mock_run.side_effect = Exception("Command not found")
    version = adapter.get_cli_version()
    assert version is None
