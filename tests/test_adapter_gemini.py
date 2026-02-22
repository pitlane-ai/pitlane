import json
from pathlib import Path

import pytest

from pitlane.adapters.gemini import GeminiAdapter
from pitlane.config import McpServerConfig


# ── identity ──────────────────────────────────────────────────────────────────


def test_cli_name():
    assert GeminiAdapter().cli_name() == "gemini"


def test_agent_type():
    assert GeminiAdapter().agent_type() == "gemini"


# ── _build_command ────────────────────────────────────────────────────────────


def test_build_command_defaults():
    adapter = GeminiAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "gemini"
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--approval-mode" in cmd
    assert "yolo" in cmd
    assert cmd[-1] == "Write hello world"


def test_build_command_with_model():
    adapter = GeminiAdapter()
    cmd = adapter._build_command("test", {"model": "gemini-2.5-pro"})
    assert "-m" in cmd
    assert "gemini-2.5-pro" in cmd


def test_build_command_no_workdir_flag():
    """Gemini uses cwd from run_streaming_sync; no explicit workdir flag."""
    adapter = GeminiAdapter()
    cmd = adapter._build_command("test", {})
    assert "--workspace" not in cmd
    assert "-C" not in cmd


# ── get_cli_version ───────────────────────────────────────────────────────────


def test_get_cli_version_success(mocker):
    adapter = GeminiAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "0.24.0\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version == "0.24.0"
    mock_run.assert_called_once_with(
        ["gemini", "--version"], capture_output=True, text=True, timeout=5
    )


def test_get_cli_version_failure(mocker):
    adapter = GeminiAdapter()
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("gemini not found"))
    assert adapter.get_cli_version() is None


# ── _parse_output ─────────────────────────────────────────────────────────────


def test_parse_output_basic():
    adapter = GeminiAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Hello from Gemini"}),
    ]
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(
        "\n".join(lines)
    )
    assert len(conversation) == 1
    assert conversation[0]["role"] == "assistant"
    assert conversation[0]["content"] == "Hello from Gemini"
    assert tool_calls_count == 0


def test_parse_output_message_type():
    adapter = GeminiAdapter()
    lines = [
        json.dumps({"type": "message", "content": "Via message type"}),
        json.dumps({"type": "content", "text": "Via content type"}),
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 2


def test_parse_output_with_tokens():
    adapter = GeminiAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Done"}),
        json.dumps(
            {"type": "usage", "usage": {"input_tokens": 200, "output_tokens": 80}}
        ),
    ]
    conversation, token_usage, cost, _ = adapter._parse_output("\n".join(lines))
    assert token_usage is not None
    assert token_usage["input"] == 200
    assert token_usage["output"] == 80


def test_parse_output_invalid_json_skipped():
    adapter = GeminiAdapter()
    lines = [
        "not json",
        json.dumps({"type": "assistant", "content": "Valid"}),
        "{bad",
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Valid"


def test_parse_output_empty():
    adapter = GeminiAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


# ── install_mcp ───────────────────────────────────────────────────────────────


def test_install_mcp_creates_file(tmp_path: Path):
    adapter = GeminiAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(
        name="gemini-server",
        type="stdio",
        command="npx",
        args=["-y", "@org/pkg"],
        env={"KEY": "val"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    target = ws / ".gemini" / "settings.json"
    assert target.exists()
    data = json.loads(target.read_text())
    assert "mcpServers" in data
    entry = data["mcpServers"]["gemini-server"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "@org/pkg"]
    assert entry["env"] == {"KEY": "val"}


def test_install_mcp_merges(tmp_path: Path):
    adapter = GeminiAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp1 = McpServerConfig(name="first", command="cmd1")
    mcp2 = McpServerConfig(name="second", command="cmd2")
    adapter.install_mcp(workspace=ws, mcp=mcp1)
    adapter.install_mcp(workspace=ws, mcp=mcp2)

    data = json.loads((ws / ".gemini" / "settings.json").read_text())
    assert "first" in data["mcpServers"]
    assert "second" in data["mcpServers"]


def test_install_mcp_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter = GeminiAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("GEMINI_TOKEN", "tok123")

    mcp = McpServerConfig(
        name="env-server",
        command="cmd",
        env={"TOKEN": "${GEMINI_TOKEN}", "STATIC": "fixed"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / ".gemini" / "settings.json").read_text())
    entry_env = data["mcpServers"]["env-server"]["env"]
    assert entry_env["TOKEN"] == "tok123"
    assert entry_env["STATIC"] == "fixed"
    assert "${GEMINI_TOKEN}" not in str(entry_env)


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_success(tmp_path, monkeypatch):
    import logging

    adapter = GeminiAdapter()
    logger = logging.getLogger("test_gemini_run")
    monkeypatch.setattr(
        "pitlane.adapters.gemini.run_streaming_sync",
        lambda *a, **kw: ("", "", 0, False),
    )
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == 0


def test_run_exception(tmp_path, monkeypatch):
    import logging

    adapter = GeminiAdapter()
    logger = logging.getLogger("test_gemini_run_exc")

    def fail(*a, **kw):
        raise RuntimeError("subprocess failed")

    monkeypatch.setattr("pitlane.adapters.gemini.run_streaming_sync", fail)
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == -1
    assert "subprocess failed" in result.stderr
