import json
from pathlib import Path

import pytest

from pitlane.adapters.cline import ClineAdapter
from pitlane.config import McpServerConfig


# ── identity ──────────────────────────────────────────────────────────────────


def test_cli_name():
    assert ClineAdapter().cli_name() == "cline"


def test_agent_type():
    assert ClineAdapter().agent_type() == "cline"


# ── _build_command ────────────────────────────────────────────────────────────


def test_build_command_defaults():
    adapter = ClineAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "cline"
    assert "--yolo" in cmd
    assert "--act" in cmd
    assert "--json" in cmd
    assert "--mode" not in cmd
    assert "--output-format" not in cmd
    assert "--oneshot" not in cmd
    assert cmd[-1] == "Write hello world"  # prompt must be last


def test_build_command_with_model():
    """Cline v2.x CLI supports -m/--model flag."""
    adapter = ClineAdapter()
    cmd = adapter._build_command("test", {"model": "claude-sonnet-4-5"})
    assert "-m" in cmd
    assert "claude-sonnet-4-5" in cmd


def test_build_command_with_workdir(tmp_path):
    adapter = ClineAdapter()
    cmd = adapter._build_command("test", {}, workdir=tmp_path)
    assert "--cwd" in cmd
    assert str(tmp_path) in cmd


# ── get_cli_version ───────────────────────────────────────────────────────────


def test_get_cli_version_success(mocker):
    adapter = ClineAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "Cline CLI Version: 1.0.9\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version == "1.0.9"
    mock_run.assert_called_once_with(
        ["cline", "version"], capture_output=True, text=True, timeout=5
    )


def test_get_cli_version_fallback_to_raw_output(mocker):
    """If 'Cline CLI Version:' pattern not found, return raw stdout."""
    adapter = ClineAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "1.0.9\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()
    assert version == "1.0.9"


def test_get_cli_version_failure(mocker):
    adapter = ClineAdapter()
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("cline not found"))
    assert adapter.get_cli_version() is None


# ── _parse_output ─────────────────────────────────────────────────────────────


def test_parse_output_basic():
    adapter = ClineAdapter()
    lines = [
        json.dumps({"type": "say", "text": "I created the file", "ts": 1234567890}),
    ]
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(
        "\n".join(lines)
    )
    assert len(conversation) == 1
    assert conversation[0]["role"] == "assistant"
    assert conversation[0]["content"] == "I created the file"
    assert tool_calls_count == 0


def test_parse_output_ask_events_ignored():
    """type=='ask' events are not collected as assistant messages."""
    adapter = ClineAdapter()
    lines = [
        json.dumps({"type": "ask", "text": "Should I proceed?", "ts": 1}),
        json.dumps({"type": "say", "text": "Done", "ts": 2}),
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Done"


def test_parse_output_with_tokens():
    adapter = ClineAdapter()
    lines = [
        json.dumps({"type": "say", "text": "Completed"}),
        json.dumps(
            {"type": "usage", "usage": {"input_tokens": 300, "output_tokens": 100}}
        ),
    ]
    conversation, token_usage, cost, _ = adapter._parse_output("\n".join(lines))
    assert token_usage is not None
    assert token_usage["input"] == 300
    assert token_usage["output"] == 100


def test_parse_output_invalid_json_skipped():
    adapter = ClineAdapter()
    lines = [
        "not json",
        json.dumps({"type": "say", "text": "Valid message"}),
        "{broken",
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Valid message"


def test_parse_output_empty():
    adapter = ClineAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


# ── install_mcp ───────────────────────────────────────────────────────────────


def test_install_mcp_creates_file(tmp_path: Path):
    adapter = ClineAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(
        name="cline-server",
        type="stdio",
        command="npx",
        args=["-y", "@org/pkg"],
        env={"KEY": "val"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    target = ws / ".cline" / "mcp.json"
    assert target.exists()
    data = json.loads(target.read_text())
    assert "mcpServers" in data
    entry = data["mcpServers"]["cline-server"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "@org/pkg"]
    assert entry["env"] == {"KEY": "val"}


def test_install_mcp_merges(tmp_path: Path):
    adapter = ClineAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp1 = McpServerConfig(name="alpha", command="cmd1")
    mcp2 = McpServerConfig(name="beta", command="cmd2")
    adapter.install_mcp(workspace=ws, mcp=mcp1)
    adapter.install_mcp(workspace=ws, mcp=mcp2)

    data = json.loads((ws / ".cline" / "mcp.json").read_text())
    assert "alpha" in data["mcpServers"]
    assert "beta" in data["mcpServers"]


def test_install_mcp_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter = ClineAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("CLINE_KEY", "mykey")

    mcp = McpServerConfig(
        name="env-server",
        command="cmd",
        env={"API_KEY": "${CLINE_KEY}", "FIXED": "value"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / ".cline" / "mcp.json").read_text())
    entry_env = data["mcpServers"]["env-server"]["env"]
    assert entry_env["API_KEY"] == "mykey"  # pragma: allowlist secret
    assert entry_env["FIXED"] == "value"
    assert "${CLINE_KEY}" not in str(entry_env)


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_success(tmp_path, monkeypatch):
    import logging

    adapter = ClineAdapter()
    logger = logging.getLogger("test_cline_run")
    monkeypatch.setattr(
        "pitlane.adapters.cline.run_streaming_sync",
        lambda *a, **kw: ("", "", 0, False),
    )
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == 0


def test_run_exception(tmp_path, monkeypatch):
    import logging

    adapter = ClineAdapter()
    logger = logging.getLogger("test_cline_run_exc")

    def fail(*a, **kw):
        raise RuntimeError("subprocess failed")

    monkeypatch.setattr("pitlane.adapters.cline.run_streaming_sync", fail)
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == -1
    assert "subprocess failed" in result.stderr
