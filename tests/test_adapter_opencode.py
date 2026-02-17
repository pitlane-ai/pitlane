import json

from pitlane.adapters.opencode import OpenCodeAdapter


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
            {"type": "tool_use", "name": "edit_file", "input": {"path": "main.tf"}}
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
            {"type": "tool_use", "name": "write", "input": {"path": "hello.py"}}
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
