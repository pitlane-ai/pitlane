import json
from pathlib import Path

import pytest

from pitlane.adapters.copilot import CopilotAdapter
from pitlane.config import McpServerConfig


# ── identity ──────────────────────────────────────────────────────────────────


def test_cli_name():
    assert CopilotAdapter().cli_name() == "copilot"


def test_agent_type():
    assert CopilotAdapter().agent_type() == "github-copilot"


# ── _build_command ────────────────────────────────────────────────────────────


def test_build_command_defaults():
    adapter = CopilotAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "copilot"
    assert "-p" in cmd
    assert "Write hello world" in cmd
    assert "--yolo" in cmd


def test_build_command_with_model():
    adapter = CopilotAdapter()
    cmd = adapter._build_command("test", {"model": "gpt-4o"})
    assert "--model" in cmd
    assert "gpt-4o" in cmd


def test_build_command_with_workdir(tmp_path):
    adapter = CopilotAdapter()
    cmd = adapter._build_command("test", {}, workdir=tmp_path)
    assert "--add-dir" in cmd
    assert str(tmp_path.resolve()) in cmd


def test_build_command_with_mcp_file(tmp_path):
    """When MCP config file exists in workdir, --additional-mcp-config is appended."""
    adapter = CopilotAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    mcp_file = ws / CopilotAdapter.MCP_FILENAME
    mcp_file.write_text(json.dumps({"mcpServers": {}}))

    cmd = adapter._build_command("test", {}, workdir=ws)
    assert "--additional-mcp-config" in cmd
    mcp_idx = cmd.index("--additional-mcp-config")
    assert cmd[mcp_idx + 1].startswith("@")
    assert CopilotAdapter.MCP_FILENAME in cmd[mcp_idx + 1]


def test_build_command_no_mcp_flag_when_file_absent(tmp_path):
    adapter = CopilotAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    cmd = adapter._build_command("test", {}, workdir=ws)
    assert "--additional-mcp-config" not in cmd


# ── get_cli_version ───────────────────────────────────────────────────────────


def test_get_cli_version_success(mocker):
    adapter = CopilotAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "GitHub Copilot CLI 0.0.414\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version == "GitHub Copilot CLI 0.0.414"
    mock_run.assert_called_once_with(
        ["copilot", "--version"], capture_output=True, text=True, timeout=5
    )


def test_get_cli_version_failure(mocker):
    adapter = CopilotAdapter()
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("copilot not found"))
    assert adapter.get_cli_version() is None


# ── _parse_output ─────────────────────────────────────────────────────────────


def test_parse_output_basic():
    adapter = CopilotAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(
        "Here is the solution."
    )
    assert len(conversation) == 1
    assert conversation[0]["role"] == "assistant"
    assert conversation[0]["content"] == "Here is the solution."
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


def test_parse_output_empty():
    adapter = CopilotAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None


def test_parse_output_whitespace_only():
    adapter = CopilotAdapter()
    conversation, _, _, _ = adapter._parse_output("   \n  \n  ")
    assert conversation == []


def test_parse_output_multiline():
    """Entire multiline stdout becomes a single assistant message."""
    adapter = CopilotAdapter()
    text = "Line one\nLine two\nLine three"
    conversation, _, _, _ = adapter._parse_output(text)
    assert len(conversation) == 1
    assert "Line one" in conversation[0]["content"]
    assert "Line three" in conversation[0]["content"]


# ── install_mcp ───────────────────────────────────────────────────────────────


def test_install_mcp_creates_file(tmp_path: Path):
    adapter = CopilotAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(
        name="copilot-server",
        type="stdio",
        command="npx",
        args=["-y", "@org/pkg"],
        env={"KEY": "val"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    target = ws / CopilotAdapter.MCP_FILENAME
    assert target.exists()
    data = json.loads(target.read_text())
    assert "mcpServers" in data
    entry = data["mcpServers"]["copilot-server"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "@org/pkg"]
    assert entry["env"] == {"KEY": "val"}


def test_install_mcp_merges(tmp_path: Path):
    adapter = CopilotAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp1 = McpServerConfig(name="server-a", command="cmd1")
    mcp2 = McpServerConfig(name="server-b", command="cmd2")
    adapter.install_mcp(workspace=ws, mcp=mcp1)
    adapter.install_mcp(workspace=ws, mcp=mcp2)

    data = json.loads((ws / CopilotAdapter.MCP_FILENAME).read_text())
    assert "server-a" in data["mcpServers"]
    assert "server-b" in data["mcpServers"]


def test_install_mcp_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter = CopilotAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("GH_TOKEN", "ghp_abc")

    mcp = McpServerConfig(
        name="env-server",
        command="cmd",
        env={"TOKEN": "${GH_TOKEN}", "LITERAL": "fixed"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / CopilotAdapter.MCP_FILENAME).read_text())
    entry_env = data["mcpServers"]["env-server"]["env"]
    assert entry_env["TOKEN"] == "ghp_abc"
    assert entry_env["LITERAL"] == "fixed"
    assert "${GH_TOKEN}" not in str(entry_env)


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_success(tmp_path, monkeypatch):
    import logging

    adapter = CopilotAdapter()
    logger = logging.getLogger("test_copilot_run")
    monkeypatch.setattr(
        "pitlane.adapters.copilot.run_streaming_sync",
        lambda *a, **kw: ("hello from copilot", "", 0, False),
    )
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == 0


def test_run_exception(tmp_path, monkeypatch):
    import logging

    adapter = CopilotAdapter()
    logger = logging.getLogger("test_copilot_run_exc")

    def fail(*a, **kw):
        raise RuntimeError("subprocess failed")

    monkeypatch.setattr("pitlane.adapters.copilot.run_streaming_sync", fail)
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == -1
    assert "subprocess failed" in result.stderr
