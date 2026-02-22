import json
from pathlib import Path

import pytest

from pitlane.adapters.codex import CodexAdapter
from pitlane.config import McpServerConfig


# ── identity ──────────────────────────────────────────────────────────────────


def test_cli_name():
    assert CodexAdapter().cli_name() == "codex"


def test_agent_type():
    assert CodexAdapter().agent_type() == "codex"


# ── _build_command ────────────────────────────────────────────────────────────


def test_build_command_defaults():
    adapter = CodexAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "codex"
    assert "exec" in cmd
    assert "--json" in cmd
    assert "--full-auto" in cmd
    assert cmd[-1] == "Write hello world"


def test_build_command_with_model():
    adapter = CodexAdapter()
    cmd = adapter._build_command("test", {"model": "o4-mini"})
    assert "-m" in cmd
    assert "o4-mini" in cmd


def test_build_command_with_workdir(tmp_path):
    adapter = CodexAdapter()
    cmd = adapter._build_command("test", {}, workdir=tmp_path)
    assert "-C" in cmd
    assert str(tmp_path) in cmd


# ── get_cli_version ───────────────────────────────────────────────────────────


def test_get_cli_version_success(mocker):
    adapter = CodexAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "codex-cli 0.101.0\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version == "codex-cli 0.101.0"
    mock_run.assert_called_once_with(
        ["codex", "--version"], capture_output=True, text=True, timeout=5
    )


def test_get_cli_version_failure(mocker):
    adapter = CodexAdapter()
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("codex not found"))
    assert adapter.get_cli_version() is None


# ── _parse_output ─────────────────────────────────────────────────────────────


def test_parse_output_basic():
    adapter = CodexAdapter()
    lines = [
        json.dumps({"type": "message", "role": "assistant", "content": "Hello world"}),
    ]
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(
        "\n".join(lines)
    )
    assert len(conversation) == 1
    assert conversation[0]["role"] == "assistant"
    assert conversation[0]["content"] == "Hello world"
    assert tool_calls_count == 0


def test_parse_output_content_list():
    """content as list of blocks (OpenAI format)."""
    adapter = CodexAdapter()
    lines = [
        json.dumps(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Block text"}],
            }
        ),
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Block text"


def test_parse_output_with_tokens():
    adapter = CodexAdapter()
    lines = [
        json.dumps({"type": "message", "role": "assistant", "content": "Done"}),
        json.dumps(
            {"type": "usage", "usage": {"input_tokens": 120, "output_tokens": 40}}
        ),
    ]
    conversation, token_usage, cost, _ = adapter._parse_output("\n".join(lines))
    assert token_usage is not None
    assert token_usage["input"] == 120
    assert token_usage["output"] == 40


def test_parse_output_invalid_json_skipped():
    adapter = CodexAdapter()
    lines = [
        "not json at all",
        json.dumps({"type": "message", "role": "assistant", "content": "Valid"}),
        "{incomplete",
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Valid"


def test_parse_output_empty():
    adapter = CodexAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


# ── install_mcp ───────────────────────────────────────────────────────────────


def test_install_mcp_creates_file(tmp_path: Path):
    adapter = CodexAdapter()
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

    target = ws / ".codex" / "config.toml"
    assert target.exists()
    content = target.read_text()
    assert "[[mcp_servers]]" in content
    assert 'name = "my-server"' in content
    assert 'command = "npx"' in content
    assert '"-y"' in content
    assert '"@org/pkg"' in content
    assert "KEY" in content
    assert "val" in content


def test_install_mcp_merges(tmp_path: Path):
    adapter = CodexAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp1 = McpServerConfig(name="server-one", command="cmd1")
    mcp2 = McpServerConfig(name="server-two", command="cmd2")
    adapter.install_mcp(workspace=ws, mcp=mcp1)
    adapter.install_mcp(workspace=ws, mcp=mcp2)

    content = (ws / ".codex" / "config.toml").read_text()
    assert "server-one" in content
    assert "server-two" in content
    assert content.count("[[mcp_servers]]") == 2


def test_install_mcp_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter = CodexAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("CODEX_SECRET", "s3cr3t")

    mcp = McpServerConfig(
        name="env-server",
        command="cmd",
        env={"SECRET": "${CODEX_SECRET}", "STATIC": "literal"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    content = (ws / ".codex" / "config.toml").read_text()
    assert "s3cr3t" in content
    assert "literal" in content
    assert "${CODEX_SECRET}" not in content


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_success(tmp_path, monkeypatch):
    import logging

    adapter = CodexAdapter()
    logger = logging.getLogger("test_codex_run")
    monkeypatch.setattr(
        "pitlane.adapters.codex.run_streaming_sync",
        lambda *a, **kw: ("", "", 0, False),
    )
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == 0


def test_run_exception(tmp_path, monkeypatch):
    import logging

    adapter = CodexAdapter()
    logger = logging.getLogger("test_codex_run_exc")

    def fail(*a, **kw):
        raise RuntimeError("subprocess failed")

    monkeypatch.setattr("pitlane.adapters.codex.run_streaming_sync", fail)
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == -1
    assert "subprocess failed" in result.stderr
