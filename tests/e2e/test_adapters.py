"""E2E smoke tests for all four adapters.

Invokes real AI assistants — requires CLIs installed and valid credentials.
Run with: uv run pytest -m e2e -v --tb=long
"""

import json
from pathlib import Path

import pytest

from pitlane.adapters.bob import BobAdapter
from pitlane.adapters.claude_code import ClaudeCodeAdapter
from pitlane.adapters.mistral_vibe import MistralVibeAdapter
from pitlane.adapters.opencode import OpenCodeAdapter
from pitlane.config import McpServerConfig

_DUMMY_MCP = McpServerConfig(name="test-server", command="echo", args=["hello"])
_CREATE_FILE_PROMPT = "Create a file called hello.txt containing 'hello world'"


@pytest.mark.e2e
@pytest.mark.usefixtures("require_claude_cli")
class TestClaudeCodeAdapter:
    def test_cli_version(self):
        version = ClaudeCodeAdapter().get_cli_version()
        assert version and len(version) > 0

    def test_run_creates_file(self, live_workspace, live_logger):
        adapter = ClaudeCodeAdapter()
        result = adapter.run(
            prompt=_CREATE_FILE_PROMPT,
            workdir=live_workspace,
            config={"model": "haiku", "timeout": 120, "max_turns": 3},
            logger=live_logger,
        )
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_seconds > 0
        assert (live_workspace / "hello.txt").exists()
        assert len(result.conversation) >= 1
        assert result.token_usage is not None
        assert result.token_usage["input"] > 0
        assert result.token_usage["output"] > 0
        assert result.tool_calls_count is not None and result.tool_calls_count > 0

    def test_install_mcp(self, live_workspace):
        ClaudeCodeAdapter().install_mcp(live_workspace, _DUMMY_MCP)
        mcp_file = live_workspace / ".mcp.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "test-server" in data["mcpServers"]

    def test_run_with_mcp(self, live_workspace, live_logger):
        mcp_server = Path(__file__).parent / "fixtures" / "mcp_test_server.py"
        mcp = McpServerConfig(
            name="pitlane-test-mcp",
            command="uv",
            args=["run", "--with", "mcp", str(mcp_server)],
        )
        adapter = ClaudeCodeAdapter()
        adapter.install_mcp(live_workspace, mcp)
        result = adapter.run(
            prompt=(
                "Use the write_marker tool from the pitlane-test-mcp server, "
                "then create hello.txt containing 'done'"
            ),
            workdir=live_workspace,
            config={"model": "haiku", "timeout": 120, "max_turns": 5},
            logger=live_logger,
        )
        assert result.exit_code == 0
        marker = live_workspace / ".mcp_marker"
        assert marker.exists()
        assert "PITLANE_MCP_MARKER_a9f3e7b2" in marker.read_text()


@pytest.mark.e2e
@pytest.mark.usefixtures("require_bob_cli")
class TestBobAdapter:
    def test_cli_version(self):
        version = BobAdapter().get_cli_version()
        assert version and len(version) > 0

    def test_run_creates_file(self, live_workspace, live_logger):
        adapter = BobAdapter()
        result = adapter.run(
            prompt=_CREATE_FILE_PROMPT,
            workdir=live_workspace,
            config={"chat_mode": "code", "timeout": 120},
            logger=live_logger,
        )
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_seconds > 0
        assert (live_workspace / "hello.txt").exists()
        assert len(result.conversation) >= 1
        assert result.token_usage is not None
        assert result.token_usage["input"] > 0
        assert result.token_usage["output"] > 0
        assert result.tool_calls_count is not None and result.tool_calls_count > 0

    def test_install_mcp(self, live_workspace):
        BobAdapter().install_mcp(live_workspace, _DUMMY_MCP)
        mcp_file = live_workspace / ".bob" / "mcp.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "test-server" in data["mcpServers"]


@pytest.mark.e2e
@pytest.mark.usefixtures("require_opencode_cli")
class TestOpenCodeAdapter:
    def test_cli_version(self):
        version = OpenCodeAdapter().get_cli_version()
        assert version and len(version) > 0

    def test_run_creates_file(self, live_workspace, live_logger):
        adapter = OpenCodeAdapter()
        result = adapter.run(
            prompt=_CREATE_FILE_PROMPT,
            workdir=live_workspace,
            config={"timeout": 120},
            logger=live_logger,
        )
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_seconds > 0
        assert (live_workspace / "hello.txt").exists()
        assert len(result.conversation) >= 1
        assert result.token_usage is not None
        assert result.token_usage["input"] > 0
        assert result.token_usage["output"] > 0
        assert result.tool_calls_count is not None and result.tool_calls_count > 0

    def test_install_mcp(self, live_workspace):
        OpenCodeAdapter().install_mcp(live_workspace, _DUMMY_MCP)
        mcp_file = live_workspace / "opencode.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "test-server" in data["mcp"]


@pytest.mark.e2e
@pytest.mark.usefixtures("require_vibe_cli")
class TestMistralVibeAdapter:
    def test_cli_version(self):
        version = MistralVibeAdapter().get_cli_version()
        assert version and len(version) > 0

    def test_run_creates_file(self, live_workspace, live_logger):
        adapter = MistralVibeAdapter()
        result = adapter.run(
            prompt=_CREATE_FILE_PROMPT,
            workdir=live_workspace,
            config={"timeout": 120, "max_turns": 3},
            logger=live_logger,
        )
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_seconds > 0
        assert (live_workspace / "hello.txt").exists()
        assert len(result.conversation) >= 1
        assert result.token_usage is not None
        assert result.token_usage["input"] > 0
        assert result.token_usage["output"] > 0
        assert result.tool_calls_count is not None and result.tool_calls_count > 0

    def test_install_mcp(self, live_workspace):
        MistralVibeAdapter().install_mcp(live_workspace, _DUMMY_MCP)
        sidecar = live_workspace / ".pitlane_mcps.json"
        assert sidecar.exists()
        entries = json.loads(sidecar.read_text())
        assert any(e["name"] == "test-server" for e in entries)
