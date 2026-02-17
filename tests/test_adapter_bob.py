import json
from pitlane.adapters.bob import BobAdapter


def test_build_command_minimal():
    adapter = BobAdapter()
    cmd = adapter._build_command("Write hello world", {})
    assert cmd[0] == "bob"
    assert "--output-format" in cmd
    assert "json" in cmd
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


def _make_stats(
    *,
    prompt_tokens=200,
    candidate_tokens=80,
    session_cost=0.0067,
    tool_calls=0,
):
    return json.dumps(
        {
            "stats": {
                "models": {
                    "main": {
                        "api": {
                            "totalRequests": 1,
                            "totalErrors": 0,
                            "totalLatencyMs": 500,
                        },
                        "tokens": {
                            "total": prompt_tokens + candidate_tokens,
                            "prompt": prompt_tokens,
                            "candidates": candidate_tokens,
                            "cached": 0,
                            "thoughts": 0,
                            "tool": 0,
                        },
                    }
                },
                "sessionCost": session_cost,
                "tools": {
                    "totalCalls": tool_calls,
                    "totalSuccess": tool_calls,
                    "totalFail": 0,
                    "totalDurationMs": 0,
                },
                "files": {"totalLinesAdded": 0, "totalLinesRemoved": 0},
            }
        }
    )


def test_parse_json_result():
    adapter = BobAdapter()
    stdout = "Hello from Bob\n" + _make_stats(
        prompt_tokens=200, candidate_tokens=80, session_cost=0.0067
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert len(conversation) == 1
    assert conversation[0]["content"] == "Hello from Bob"
    assert token_usage["input"] == 200
    assert token_usage["output"] == 80
    assert cost == 0.0067
    assert tool_calls_count == 0


def test_parse_json_with_tool_calls():
    adapter = BobAdapter()
    stdout = "Done\n" + _make_stats(
        prompt_tokens=50, candidate_tokens=20, session_cost=0.001, tool_calls=3
    )
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert tool_calls_count == 3
    assert token_usage["input"] == 50
    assert token_usage["output"] == 20
    assert cost == 0.001


def test_parse_json_no_response_text():
    adapter = BobAdapter()
    # Stats block only, no preceding text
    stdout = _make_stats(prompt_tokens=100, candidate_tokens=40, session_cost=0.002)
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert conversation == []
    assert token_usage["input"] == 100
    assert token_usage["output"] == 40
    assert cost == 0.002


def test_parse_json_strips_ansi():
    adapter = BobAdapter()
    ansi_text = "\x1b[32mHello\x1b[0m from Bob"
    stdout = ansi_text + "\n" + _make_stats()
    conversation, _, _, _ = adapter._parse_output(stdout)
    assert conversation[0]["content"] == "Hello from Bob"


def test_parse_json_no_stats_block():
    adapter = BobAdapter()
    stdout = "plain text with no JSON"
    conversation, token_usage, cost, tool_calls_count = adapter._parse_output(stdout)
    assert conversation == []
    assert token_usage is None
    assert cost is None
    assert tool_calls_count == 0


def test_parse_json_multi_tier():
    adapter = BobAdapter()
    # Two model tiers whose tokens should be aggregated
    stats = json.dumps(
        {
            "stats": {
                "models": {
                    "fast": {
                        "api": {"totalRequests": 2, "totalErrors": 0, "totalLatencyMs": 100},
                        "tokens": {
                            "total": 150,
                            "prompt": 100,
                            "candidates": 50,
                            "cached": 0,
                            "thoughts": 0,
                            "tool": 0,
                        },
                    },
                    "main": {
                        "api": {"totalRequests": 1, "totalErrors": 0, "totalLatencyMs": 400},
                        "tokens": {
                            "total": 130,
                            "prompt": 80,
                            "candidates": 50,
                            "cached": 0,
                            "thoughts": 0,
                            "tool": 0,
                        },
                    },
                },
                "sessionCost": 0.005,
                "tools": {"totalCalls": 0, "totalSuccess": 0, "totalFail": 0, "totalDurationMs": 0},
                "files": {"totalLinesAdded": 0, "totalLinesRemoved": 0},
            }
        }
    )
    stdout = "response\n" + stats
    _, token_usage, cost, _ = adapter._parse_output(stdout)
    assert token_usage["input"] == 180   # 100 + 80
    assert token_usage["output"] == 100  # 50 + 50
    assert cost == 0.005
