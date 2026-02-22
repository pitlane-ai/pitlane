import json
from pathlib import Path

import pytest

from pitlane.adapters.kilo import KiloAdapter
from pitlane.config import McpServerConfig


# ── identity ──────────────────────────────────────────────────────────────────


def test_cli_name():
    assert KiloAdapter().cli_name() == "kilo"


def test_agent_type():
    assert KiloAdapter().agent_type() == "kilo"


# ── _build_command ────────────────────────────────────────────────────────────


def test_build_command_defaults():
    adapter = KiloAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "kilo"
    assert cmd[1] == "run"
    assert "--auto" in cmd
    assert "--format" in cmd
    assert "json" in cmd
    assert "--prompt" not in cmd
    assert cmd[-1] == "Write hello world"


def test_build_command_with_model():
    adapter = KiloAdapter()
    cmd = adapter._build_command("test", {"model": "anthropic/claude-sonnet-4-5"})
    assert "-m" in cmd
    assert "anthropic/claude-sonnet-4-5" in cmd


def test_build_command_with_agent():
    adapter = KiloAdapter()
    cmd = adapter._build_command("test", {"agent": "coder"})
    assert "--agent" in cmd
    assert "coder" in cmd


def test_build_command_no_workdir_flag():
    """Kilo uses cwd from run_streaming_sync; no explicit workdir flag."""
    adapter = KiloAdapter()
    cmd = adapter._build_command("test", {})
    assert "--workspace" not in cmd
    assert "-C" not in cmd


# ── get_cli_version ───────────────────────────────────────────────────────────


def test_get_cli_version_success(mocker):
    adapter = KiloAdapter()
    mock_run = mocker.patch("subprocess.run")
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "kilo 1.0.25\n"
    mock_run.return_value = mock_result

    version = adapter.get_cli_version()

    assert version == "kilo 1.0.25"
    mock_run.assert_called_once_with(
        ["kilo", "--version"], capture_output=True, text=True, timeout=5
    )


def test_get_cli_version_failure(mocker):
    adapter = KiloAdapter()
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("kilo not found"))
    assert adapter.get_cli_version() is None


# ── _parse_output ─────────────────────────────────────────────────────────────


def test_parse_output_basic():
    adapter = KiloAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Hello from Kilo"}),
    ]
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(
        "\n".join(lines)
    )
    assert len(conversation) == 1
    assert conversation[0]["role"] == "assistant"
    assert conversation[0]["content"] == "Hello from Kilo"
    assert tool_calls_count == 0


def test_parse_output_with_tokens():
    """step_finish events carry token/cost data (same as OpenCode)."""
    adapter = KiloAdapter()
    lines = [
        json.dumps({"type": "assistant", "content": "Done"}),
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {"input": 500, "output": 150},
                    "cost": 0.01,
                },
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {"input": 200, "output": 50},
                    "cost": 0.005,
                },
            }
        ),
    ]
    conversation, token_usage, cost, _ = adapter._parse_output("\n".join(lines))
    assert token_usage is not None
    assert token_usage["input"] == 700
    assert token_usage["output"] == 200
    assert cost == pytest.approx(0.015)


def test_parse_output_invalid_json_skipped():
    adapter = KiloAdapter()
    lines = [
        "not json",
        json.dumps({"type": "assistant", "content": "Valid"}),
        "{incomplete",
    ]
    conversation, _, _, _ = adapter._parse_output("\n".join(lines))
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Valid"


def test_parse_output_tool_use():
    adapter = KiloAdapter()
    lines = [
        json.dumps(
            {"type": "tool_use", "name": "write_file", "input": {"path": "out.py"}}
        ),
        json.dumps({"type": "assistant", "content": "File written"}),
    ]
    conversation, _, _, tool_calls_count = adapter._parse_output("\n".join(lines))
    assert tool_calls_count == 1
    assert len(conversation) == 2
    assert conversation[0]["tool_use"]["name"] == "write_file"


def test_parse_output_empty():
    adapter = KiloAdapter()
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output("")
    assert conversation == []
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


# ── install_mcp ───────────────────────────────────────────────────────────────


def test_install_mcp_creates_file(tmp_path: Path):
    adapter = KiloAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    mcp = McpServerConfig(
        name="kilo-server",
        type="stdio",
        command="npx",
        args=["-y", "@org/pkg"],
        env={"TOKEN": "abc"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    target = ws / "kilo.json"
    assert target.exists()
    data = json.loads(target.read_text())
    entry = data["mcp"]["kilo-server"]
    assert entry["type"] == "local"
    assert entry["command"] == ["npx", "-y", "@org/pkg"]
    assert entry["environment"] == {"TOKEN": "abc"}
    assert entry["enabled"] is True


def test_install_mcp_merges(tmp_path: Path):
    adapter = KiloAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()

    existing = {"mcp": {"old": {"type": "local", "command": []}}}
    (ws / "kilo.json").write_text(json.dumps(existing))

    mcp = McpServerConfig(name="new-server", command="cmd")
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / "kilo.json").read_text())
    assert "old" in data["mcp"]
    assert "new-server" in data["mcp"]


def test_install_mcp_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter = KiloAdapter()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("KILO_SECRET", "k1losecret")

    mcp = McpServerConfig(
        name="env-server",
        command="cmd",
        env={"SECRET": "${KILO_SECRET}", "PLAIN": "text"},
    )
    adapter.install_mcp(workspace=ws, mcp=mcp)

    data = json.loads((ws / "kilo.json").read_text())
    env = data["mcp"]["env-server"]["environment"]
    assert env["SECRET"] == "k1losecret"  # pragma: allowlist secret
    assert env["PLAIN"] == "text"
    assert "${KILO_SECRET}" not in str(env)


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_success(tmp_path, monkeypatch):
    import logging

    adapter = KiloAdapter()
    logger = logging.getLogger("test_kilo_run")
    monkeypatch.setattr(
        "pitlane.adapters.kilo.run_streaming_sync",
        lambda *a, **kw: ("", "", 0, False),
    )
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == 0


def test_run_exception(tmp_path, monkeypatch):
    import logging

    adapter = KiloAdapter()
    logger = logging.getLogger("test_kilo_run_exc")

    def fail(*a, **kw):
        raise RuntimeError("subprocess failed")

    monkeypatch.setattr("pitlane.adapters.kilo.run_streaming_sync", fail)
    result = adapter.run("test prompt", tmp_path, {}, logger)
    assert result.exit_code == -1
    assert "subprocess failed" in result.stderr
