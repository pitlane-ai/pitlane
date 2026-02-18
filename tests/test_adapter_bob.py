import json
from pitlane.adapters.bob import BobAdapter


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
    return json.dumps({
        "type": "result",
        "status": "success",
        "stats": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "duration_ms": 500,
            "tool_calls": tool_calls,
        }
    })


def _make_completion_event(text="Hello from Bob"):
    return json.dumps({
        "type": "tool_use",
        "tool_name": "attempt_completion",
        "tool_id": "tool-1",
        "parameters": {"result": text},
    })


def _make_cost_message(cost=0.09):
    return json.dumps({
        "type": "message",
        "role": "assistant",
        "delta": True,
        "content": f"[using tool attempt_completion: Successfully completed | Cost: {cost}]\n",
    })


def test_parse_json_result():
    adapter = BobAdapter()
    stdout = "\n".join([
        _make_completion_event("Hello from Bob"),
        _make_cost_message(0.09),
        _make_result_event(input_tokens=200, output_tokens=80),
    ])
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Hello from Bob"
    assert token_usage["input"] == 200
    assert token_usage["output"] == 80
    assert cost == 0.09
    assert tool_calls_count == 0


def test_parse_json_with_tool_calls():
    adapter = BobAdapter()
    tool_event = json.dumps({
        "type": "tool_use",
        "tool_name": "bash",
        "tool_id": "tool-2",
        "parameters": {"command": "ls"},
    })
    stdout = "\n".join([
        tool_event,
        tool_event,
        tool_event,
        _make_completion_event("Done"),
        _make_cost_message(0.15),
        _make_result_event(input_tokens=50, output_tokens=20, tool_calls=3),
    ])
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
    stdout = "\n".join([
        "YOLO mode is enabled. All tool calls will be automatically approved.",
        "---output---",
        _make_completion_event("Hello from Bob"),
        "---output---",
        _make_result_event(input_tokens=10, output_tokens=5),
    ])
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
    stdout = "\n".join([
        _make_completion_event("Done"),
        _make_cost_message(0.42),
        _make_result_event(input_tokens=100, output_tokens=50),
    ])
    _, _, cost, _ = adapter._parse_output(stdout)
    assert cost == 0.42


def test_parse_non_cost_message_does_not_set_cost():
    adapter = BobAdapter()
    non_cost_message = json.dumps({
        "type": "message",
        "role": "assistant",
        "delta": True,
        "content": "[using tool write_to_file: Writing to fib.py]\n",
    })
    stdout = "\n".join([
        non_cost_message,
        _make_completion_event("Done"),
        _make_result_event(input_tokens=10, output_tokens=5),
    ])
    _, _, cost, _ = adapter._parse_output(stdout)
    assert cost is None
