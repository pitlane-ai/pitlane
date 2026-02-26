import pytest
import textwrap
import yaml
from concurrent.futures import as_completed
from unittest.mock import patch
from junitparser import JUnitXml
from pitlane.runner import Runner, IterationResult
from pitlane.metrics import compute_stats, aggregate_results
from pitlane.assistants.base import AssistantResult
from pitlane.config import load_config


@pytest.fixture
def eval_config(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / ".gitkeep").write_text("")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    type: claude-code
    args:
      model: sonnet

tasks:
  - name: simple-test
    prompt: "Create hello.py"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "hello.py"
""")
    return load_config(config_file)


def test_runner_creates_run_directory(mocker, tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)

    mock_result = AssistantResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )
    mocker.patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    )
    run_dir = runner.execute()

    assert run_dir.exists()
    assert (run_dir / "junit.xml").exists()
    assert (run_dir / "meta.yaml").exists()
    assert (run_dir / "debug.log").exists()
    assert not (run_dir / "results.json").exists()


def test_runner_captures_results(mocker, tmp_path, eval_config):
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)

    mock_result = AssistantResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
        token_usage={"input": 100, "output": 50},
        cost_usd=0.01,
    )
    mocker.patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    )
    run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "mock-claude / simple-test" in suite_names
    suite = next(s for s in xml if s.name == "mock-claude / simple-test")
    assert suite.tests >= 1
    props = {p.name for p in suite.properties()}
    assert "weighted_score" in props
    assert "assertion_pass_rate" in props


def test_runner_parallel_execution(mocker, tmp_path, eval_config):
    """Test that parallel execution works correctly."""
    # Create a config with multiple tasks
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "test.txt").write_text("test")

    config_file = tmp_path / "parallel_eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    type: claude-code
    args:
      model: sonnet

tasks:
  - name: task-1
    prompt: "Task 1"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-2
    prompt: "Task 2"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-3
    prompt: "Task 3"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
""")
    parallel_config = load_config(config_file)

    runner = Runner(
        config=parallel_config,
        output_dir=tmp_path / "runs",
        verbose=False,
        parallel_tasks=2,
    )

    mock_result = AssistantResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=0.1,
    )
    mocker.patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    )
    run_dir = runner.execute()

    # Verify all tasks completed successfully
    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "mock-claude / task-1" in suite_names
    assert "mock-claude / task-2" in suite_names
    assert "mock-claude / task-3" in suite_names
    assert len(suite_names) == 3

    # Verify all suites have test cases and properties
    for suite in xml:
        assert suite.tests >= 1
        props = {p.name for p in suite.properties()}
        assert "assertion_pass_rate" in props


def test_runner_sequential_execution(mocker, tmp_path, eval_config):
    """Test that sequential execution works when parallel_tasks=1."""
    runner = Runner(
        config=eval_config,
        output_dir=tmp_path / "runs",
        verbose=False,
        parallel_tasks=1,
    )

    mock_result = AssistantResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )
    mocker.patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    )
    run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "mock-claude / simple-test" in suite_names


def test_runner_default_parallel_tasks(tmp_path, eval_config):
    """Test that default parallel_tasks is 1 (sequential)."""
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)
    assert runner.parallel_tasks == 1


def test_runner_default_repeat(tmp_path, eval_config):
    """Test that default repeat is 1."""
    runner = Runner(config=eval_config, output_dir=tmp_path / "runs", verbose=False)
    assert runner.repeat == 1


def test_runner_repeat_execution(mocker, tmp_path, eval_config):
    """Test that repeat=3 runs the task 3 times and aggregates results."""
    runner = Runner(
        config=eval_config, output_dir=tmp_path / "runs", verbose=False, repeat=3
    )

    call_count = 0

    def mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return AssistantResult(
            stdout="",
            stderr="",
            exit_code=0,
            duration_seconds=float(call_count),
            token_usage={"input": 100 * call_count, "output": 50 * call_count},
            cost_usd=0.01 * call_count,
        )

    mocker.patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run", side_effect=mock_run
    )
    run_dir = runner.execute()

    assert call_count == 3

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite = next(s for s in xml if s.name == "mock-claude / simple-test")

    # Repeat stats are stored as properties
    props = {p.name: p.value for p in suite.properties()}
    assert "wall_clock_seconds_avg" in props
    assert "wall_clock_seconds_min" in props
    assert "wall_clock_seconds_max" in props
    assert "wall_clock_seconds_stddev" in props

    # avg wall_clock_seconds == (1+2+3)/3 == 2.0
    assert float(props["wall_clock_seconds_avg"]) == pytest.approx(2.0)


def test_runner_repeat_meta_includes_repeat_count(mocker, tmp_path, eval_config):
    """Test that meta.yaml includes the repeat count."""
    import yaml

    runner = Runner(
        config=eval_config, output_dir=tmp_path / "runs", verbose=False, repeat=5
    )

    mock_result = AssistantResult(
        stdout="",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )
    mocker.patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    )
    run_dir = runner.execute()

    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    assert meta["repeat"] == 5


def test_compute_stats_basic():
    """Test compute_stats with normal values."""
    stats = compute_stats([1.0, 2.0, 3.0])
    assert stats.avg == 2.0
    assert stats.min == 1.0
    assert stats.max == 3.0
    assert stats.stddev == 0.8165  # population std dev


def test_compute_stats_single_value():
    """Test compute_stats with a single value."""
    stats = compute_stats([5.0])
    assert stats.avg == 5.0
    assert stats.min == 5.0
    assert stats.max == 5.0
    assert stats.stddev == 0.0


def test_compute_stats_with_nones():
    """Test compute_stats filters out None values."""
    stats = compute_stats([1.0, None, 3.0])
    assert stats.avg == 2.0
    assert stats.min == 1.0
    assert stats.max == 3.0


def test_compute_stats_all_nones():
    """Test compute_stats with all None values."""
    stats = compute_stats([None, None])
    assert stats.avg is None
    assert stats.min is None
    assert stats.max is None
    assert stats.stddev is None


def test_aggregate_results():
    """Test aggregate_results produces correct structure."""

    run_results = [
        IterationResult(
            metrics={
                "wall_clock_seconds": 1.0,
                "exit_code": 0,
                "assertion_pass_rate": 100.0,
            },
            assertions=[
                {"name": "file_exists:test.py", "passed": True, "message": "exists"}
            ],
            all_passed=True,
        ),
        IterationResult(
            metrics={
                "wall_clock_seconds": 3.0,
                "exit_code": 0,
                "assertion_pass_rate": 100.0,
            },
            assertions=[
                {"name": "file_exists:test.py", "passed": True, "message": "exists"}
            ],
            all_passed=True,
        ),
        IterationResult(
            metrics={
                "wall_clock_seconds": 2.0,
                "exit_code": 1,
                "assertion_pass_rate": 0.0,
            },
            assertions=[
                {"name": "file_exists:test.py", "passed": False, "message": "not found"}
            ],
            all_passed=False,
        ),
    ]

    result = aggregate_results(run_results)

    assert result.repeat.count == 3
    assert result.repeat.all_passed_count == 2
    assert result.repeat.all_passed_rate == pytest.approx(66.7, abs=0.1)
    assert result.all_passed is False

    # Metrics should be averages
    assert result.metrics["wall_clock_seconds"] == 2.0

    # Stats
    assert result.metrics_stats["wall_clock_seconds"].avg == 2.0
    assert result.metrics_stats["wall_clock_seconds"].min == 1.0
    assert result.metrics_stats["wall_clock_seconds"].max == 3.0

    # Assertions summary
    assert len(result.assertions) == 1
    assert result.assertions[0].pass_rate == pytest.approx(66.7, abs=0.1)
    assert result.assertions[0].message == "Passed 2/3 iterations"

    # Iterations preserved
    assert len(result.repeat.iterations) == 3


def test_runner_interrupt_saves_partial_results(mocker, tmp_path):
    """Test that interrupting a run saves partial results and generates report."""
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "test.txt").write_text("test")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    type: claude-code
    args:
      model: sonnet

tasks:
  - name: task-1
    prompt: "Task 1"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-2
    prompt: "Task 2"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-3
    prompt: "Task 3"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
""")
    config = load_config(config_file)

    completed_result = {
        "metrics": {
            "wall_clock_seconds": 0.1,
            "exit_code": 0,
            "files_created": 0,
            "files_modified": 0,
            "total_lines_generated": 0,
            "token_usage_input": 0,
            "token_usage_output": 0,
            "cost_usd": 0.0,
            "tool_calls_count": 0,
            "assertion_pass_count": 1,
            "assertion_fail_count": 0,
            "assertion_pass_rate": 100.0,
            "weighted_score": 100.0,
        },
        "assertions": [
            {
                "name": "file_exists: test.txt",
                "passed": True,
                "message": "ok",
                "score": 1.0,
                "weight": 1.0,
            }
        ],
        "all_passed": True,
    }

    original_as_completed = as_completed

    def mock_as_completed(futures):
        """Yield one completed future then raise KeyboardInterrupt."""
        iterator = original_as_completed(futures)
        yield next(iterator)
        raise KeyboardInterrupt()

    runner = Runner(
        config=config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1
    )

    mocker.patch.object(runner, "_run_task", return_value=completed_result)
    mocker.patch("pitlane.runner.as_completed", side_effect=mock_as_completed)
    run_dir = runner.execute()

    # Runner should be marked as interrupted
    assert runner.interrupted is True

    # Partial results should be saved
    assert (run_dir / "junit.xml").exists()
    assert (run_dir / "meta.yaml").exists()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suites = list(xml)
    # At least one task should have completed
    assert len(suites) >= 1

    # Verify suites have test cases and properties
    for suite in suites:
        assert suite.tests >= 1
        props = {p.name for p in suite.properties()}
        assert "assertion_pass_rate" in props

    # Meta should indicate interrupted
    meta = yaml.safe_load((run_dir / "meta.yaml").read_text())
    assert meta["interrupted"] is True


@pytest.fixture
def multi_assistant_config(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / ".gitkeep").write_text("")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  a:
    type: claude-code
    args:
      model: sonnet
  b:
    type: claude-code
    args:
      model: sonnet
  c:
    type: claude-code
    args:
      model: sonnet

tasks:
  - name: simple-test
    prompt: "Create hello.py"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: ".gitkeep"
""")
    return load_config(config_file)


def test_assistant_filter_single(tmp_path, multi_assistant_config):
    runner = Runner(
        config=multi_assistant_config,
        output_dir=tmp_path / "runs",
        assistant_filter=["a"],
    )
    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )
    with patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "a / simple-test" in suite_names
    assert "b / simple-test" not in suite_names
    assert "c / simple-test" not in suite_names


def test_assistant_filter_multiple(tmp_path, multi_assistant_config):
    runner = Runner(
        config=multi_assistant_config,
        output_dir=tmp_path / "runs",
        assistant_filter=["a", "b"],
    )
    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )
    with patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "a / simple-test" in suite_names
    assert "b / simple-test" in suite_names
    assert "c / simple-test" not in suite_names


def test_skip_assistants_single(tmp_path, multi_assistant_config):
    runner = Runner(
        config=multi_assistant_config,
        output_dir=tmp_path / "runs",
        skip_assistants=["a"],
    )
    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )
    with patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "a / simple-test" not in suite_names
    assert "b / simple-test" in suite_names
    assert "c / simple-test" in suite_names


def test_skip_assistants_multiple(tmp_path, multi_assistant_config):
    runner = Runner(
        config=multi_assistant_config,
        output_dir=tmp_path / "runs",
        skip_assistants=["a", "b"],
    )
    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )
    with patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "a / simple-test" not in suite_names
    assert "b / simple-test" not in suite_names
    assert "c / simple-test" in suite_names


def test_only_and_skip_combined(tmp_path, multi_assistant_config):
    runner = Runner(
        config=multi_assistant_config,
        output_dir=tmp_path / "runs",
        assistant_filter=["a", "b"],
        skip_assistants=["b"],
    )
    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )
    with patch(
        "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
        return_value=mock_result,
    ):
        run_dir = runner.execute()

    xml = JUnitXml.fromfile(str(run_dir / "junit.xml"))
    suite_names = {s.name for s in xml}
    assert "a / simple-test" in suite_names
    assert "b / simple-test" not in suite_names
    assert "c / simple-test" not in suite_names


def test_runner_interrupt_report_generation(mocker, tmp_path):
    """Test that a report can be generated from partial results."""
    from pitlane.reporting.junit import generate_report

    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "test.txt").write_text("test")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(f"""
assistants:
  mock-claude:
    type: claude-code
    args:
      model: sonnet

tasks:
  - name: task-1
    prompt: "Task 1"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
  - name: task-2
    prompt: "Task 2"
    workdir: {fixture_dir}
    timeout: 10
    assertions:
      - file_exists: "test.txt"
""")
    config = load_config(config_file)

    completed_result = {
        "metrics": {
            "wall_clock_seconds": 0.1,
            "exit_code": 0,
            "files_created": 0,
            "files_modified": 0,
            "total_lines_generated": 0,
            "token_usage_input": 0,
            "token_usage_output": 0,
            "cost_usd": 0.0,
            "tool_calls_count": 0,
            "assertion_pass_count": 1,
            "assertion_fail_count": 0,
            "assertion_pass_rate": 100.0,
            "weighted_score": 100.0,
        },
        "assertions": [
            {
                "name": "file_exists: test.txt",
                "passed": True,
                "message": "ok",
                "score": 1.0,
                "weight": 1.0,
            }
        ],
        "all_passed": True,
    }

    original_as_completed = as_completed

    def mock_as_completed(futures):
        iterator = original_as_completed(futures)
        yield next(iterator)
        raise KeyboardInterrupt()

    runner = Runner(
        config=config, output_dir=tmp_path / "runs", verbose=False, parallel_tasks=1
    )

    mocker.patch.object(runner, "_run_task", return_value=completed_result)
    mocker.patch("pitlane.runner.as_completed", side_effect=mock_as_completed)
    run_dir = runner.execute()

    # Report should be generatable from partial results
    report_path = generate_report(run_dir)
    assert report_path.exists()
    html_content = report_path.read_text()
    assert "task-" in html_content


def test_runner_calls_install_mcp_for_each_mcp(tmp_path):
    """Runner calls adapter.install_mcp for each MCP in assistant_config.mcps."""
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / ".gitkeep").write_text("")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(
        textwrap.dedent(f"""\
        assistants:
          mcp-assistant:
            type: claude-code
            args:
              model: haiku
            mcps:
              - name: server-a
                command: npx
                args: ["-y", "@org/a"]
              - name: server-b
                type: sse
                url: "http://localhost:9000/sse"

        tasks:
          - name: simple-test
            prompt: "Create hello.py"
            workdir: {fixture_dir}
            timeout: 10
            assertions:
              - file_exists: "hello.py"
        """)
    )
    config = load_config(config_file)

    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )

    install_mcp_calls = []

    def fake_install_mcp(workspace, mcp):
        install_mcp_calls.append(mcp.name)

    with (
        patch(
            "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
            return_value=mock_result,
        ),
        patch(
            "pitlane.assistants.claude_code.ClaudeCodeAssistant.install_mcp",
            side_effect=fake_install_mcp,
        ),
    ):
        runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
        runner.execute()

    assert len(install_mcp_calls) == 2
    assert "server-a" in install_mcp_calls
    assert "server-b" in install_mcp_calls


def test_runner_no_mcps_does_not_call_install_mcp(tmp_path):
    """Runner does not call install_mcp when assistant has no mcps."""
    fixture_dir = tmp_path / "fixtures" / "empty"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / ".gitkeep").write_text("")

    config_file = tmp_path / "eval.yaml"
    config_file.write_text(
        textwrap.dedent(f"""\
        assistants:
          baseline:
            type: claude-code
            args:
              model: haiku

        tasks:
          - name: t
            prompt: p
            workdir: {fixture_dir}
            timeout: 10
            assertions:
              - command_succeeds: "true"
        """)
    )
    config = load_config(config_file)

    mock_result = AssistantResult(
        stdout="", stderr="", exit_code=0, duration_seconds=1.0
    )

    with (
        patch(
            "pitlane.assistants.claude_code.ClaudeCodeAssistant.run",
            return_value=mock_result,
        ),
        patch(
            "pitlane.assistants.claude_code.ClaudeCodeAssistant.install_mcp"
        ) as mock_install_mcp,
    ):
        runner = Runner(config=config, output_dir=tmp_path / "runs", verbose=False)
        runner.execute()

    mock_install_mcp.assert_not_called()
