from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from junitparser import TestCase, TestSuite, JUnitXml, Failure


def _build_workspace_tree(workspace_dir: Path) -> dict:
    """Return nested dict: dirs are dicts, files are {"_file": True, "content": str, "path": str}."""
    tree: dict = {}
    for f in sorted(workspace_dir.rglob("*")):
        if not f.is_file():
            continue
        parts = f.relative_to(workspace_dir).parts
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            content = "\n".join(lines[:200])
            if len(lines) > 200:
                content += f"\n... ({len(lines) - 200} more lines)"
        except Exception:
            content = "(could not read file)"
        node[parts[-1]] = {
            "_file": True,
            "content": content,
            "path": str(f.relative_to(workspace_dir)),
        }
    return tree


def write_junit(run_dir: Path, all_results: dict[str, dict[str, Any]]) -> Path:
    """Write junit.xml from aggregated results dict, return path."""
    xml = JUnitXml()

    for assistant_name, assistant_results in all_results.items():
        for task_name, task_result in assistant_results.items():
            metrics = task_result.get("metrics", {})
            assertions = task_result.get("assertions", [])
            metrics_stats = task_result.get("metrics_stats", {})

            suite = TestSuite(f"{assistant_name} / {task_name}")

            # Core metric properties
            prop_keys = [
                "cost_usd",
                "token_usage_input",
                "token_usage_output",
                "weighted_score",
                "assertion_pass_rate",
                "files_created",
                "files_modified",
                "tool_calls_count",
                "timed_out",
            ]
            for key in prop_keys:
                val = metrics.get(key)
                if val is not None:
                    suite.add_property(key, str(val))

            # Repeat-mode stats: emit as {metric}_{stat} properties
            if metrics_stats:
                for metric_name, stats in metrics_stats.items():
                    if isinstance(stats, dict):
                        for stat_name in ("avg", "stddev", "min", "max"):
                            stat_val = stats.get(stat_name)
                            if stat_val is not None:
                                suite.add_property(
                                    f"{metric_name}_{stat_name}", str(stat_val)
                                )

            # Test cases: one per assertion
            for assertion in assertions:
                case = TestCase(assertion["name"])
                case.classname = task_name
                if not assertion.get("passed", True):
                    case.result = Failure(assertion.get("message", ""))
                suite.add_testcase(case)

            # Set time after add_testcase (add_testcase resets it via update_statistics)
            suite.time = float(metrics.get("wall_clock_seconds") or 0.0)

            # Use append (not +=) to preserve properties and time
            xml.append(suite)

    junit_path = run_dir / "junit.xml"
    xml.write(str(junit_path), pretty=True)
    return junit_path


def generate_report(run_dir: Path) -> Path:
    """Render junit.xml → report.html using Jinja2 template, return path."""
    import yaml
    from jinja2 import Environment, FileSystemLoader
    from junitparser import JUnitXml

    junit_path = run_dir / "junit.xml"
    report_path = run_dir / "report.html"

    # Load run metadata
    meta: dict = {}
    meta_path = run_dir / "meta.yaml"
    if meta_path.exists():
        try:
            meta = yaml.safe_load(meta_path.read_text()) or {}
        except Exception:
            pass

    xml = JUnitXml.fromfile(str(junit_path))

    suites = []
    for suite in xml:
        cases = []
        for case in suite:
            result = None
            if case.result:
                result = {
                    "status": type(case.result[0]).__name__,
                    "message": case.result[0].message or "",
                }
            cases.append(
                {"name": case.name, "classname": case.classname, "result": result}
            )

        props = {p.name: p.value for p in suite.properties()}

        # Load per-suite disk data
        conversation: list = []
        debug_log: str = ""
        workspace_files: list = []
        workspace_tree: dict = {}

        parts = suite.name.split(" / ", 1)
        if len(parts) == 2:
            assistant_name, task_name = parts
            iter_dir = run_dir / assistant_name / task_name / "iter-0"

            conv_path = iter_dir / "conversation.json"
            if conv_path.exists():
                try:
                    conversation = json.loads(conv_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            debug_path = iter_dir / "debug.log"
            if debug_path.exists():
                try:
                    debug_log = debug_path.read_text(encoding="utf-8")
                except Exception:
                    pass

            workspace_dir = iter_dir / "workspace"
            if workspace_dir.exists():
                workspace_files = sorted(
                    str(f.relative_to(workspace_dir))
                    for f in workspace_dir.rglob("*")
                    if f.is_file()
                )
                workspace_tree = _build_workspace_tree(workspace_dir)

        suites.append(
            {
                "name": suite.name,
                "tests": suite.tests,
                "failures": suite.failures,
                "errors": suite.errors,
                "skipped": suite.skipped,
                "time": suite.time,
                "properties": props,
                "cases": cases,
                "conversation": conversation,
                "debug_log": debug_log,
                "workspace_files": workspace_files,
                "workspace_tree": workspace_tree,
            }
        )

    # Add assistant_name field to each suite
    for s in suites:
        parts_s = s["name"].split(" / ", 1)
        s["assistant_name"] = parts_s[0] if len(parts_s) == 2 else s["name"]

    # Group suites by task name (preserving insertion order)
    task_groups: dict[str, list] = {}
    for s in suites:
        parts_s = s["name"].split(" / ", 1)
        task = parts_s[1] if len(parts_s) == 2 else s["name"]
        task_groups.setdefault(task, []).append(s)

    # Sort each task group by weighted_score descending (highest first)
    for agents in task_groups.values():
        agents.sort(
            key=lambda s: float(s["properties"].get("weighted_score", -1)),
            reverse=True,
        )

    tasks = list(task_groups.items())  # [(task_name, [suite, ...]), ...]

    total_tests = sum(s["tests"] for s in suites)
    total_failures = sum(s["failures"] for s in suites)
    total_errors = sum(s["errors"] for s in suites)
    total_configurations = len(suites)

    # Compute average weighted score across all configurations
    scores = []
    for s in suites:
        ws = s["properties"].get("weighted_score")
        if ws is not None:
            try:
                scores.append(float(ws))
            except (ValueError, TypeError):
                pass
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    # Build chart data for scatter plots and distribution charts
    chart_data = []
    for s in suites:
        props = s["properties"]
        ws = props.get("weighted_score")
        if ws is None:
            continue
        try:
            score_val = float(ws)
        except (ValueError, TypeError):
            continue

        cost = None
        cost_raw = props.get("cost_usd")
        if cost_raw is not None:
            try:
                cost = float(cost_raw)
            except (ValueError, TypeError):
                pass

        latency = None
        if s.get("time") is not None:
            try:
                latency = float(s["time"])
            except (ValueError, TypeError):
                pass

        score_stddev = None
        stddev_raw = props.get("weighted_score_stddev")
        if stddev_raw is not None:
            try:
                score_stddev = float(stddev_raw)
            except (ValueError, TypeError):
                pass

        def _float_prop(key: str) -> float | None:
            raw = props.get(key)
            if raw is None:
                return None
            try:
                return float(raw)
            except (ValueError, TypeError):
                return None

        inp = _float_prop("token_usage_input")
        out = _float_prop("token_usage_output")
        total_tokens = (
            (inp or 0) + (out or 0) if (inp is not None or out is not None) else None
        )

        chart_data.append(
            {
                "label": s["name"],
                "assistant": s.get("assistant_name", s["name"]),
                "score": score_val,
                "cost": cost,
                "latency": latency,
                "score_stddev": score_stddev,
                "tool_calls_count": _float_prop("tool_calls_count"),
                "token_usage_input": inp,
                "token_usage_output": out,
                "total_tokens": total_tokens,
                "files_created": _float_prop("files_created"),
                "files_modified": _float_prop("files_modified"),
                "total_lines_generated": _float_prop("total_lines_generated"),
                "assertion_pass_rate": _float_prop("assertion_pass_rate"),
            }
        )

    chart_data_json = json.dumps(chart_data)

    tmpl_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)), autoescape=True)
    template = env.get_template("report.html.j2")

    html = template.render(
        suites=suites,
        tasks=tasks,
        total_tests=total_tests,
        total_failures=total_failures,
        total_errors=total_errors,
        total_configurations=total_configurations,
        avg_score=avg_score,
        chart_data_json=chart_data_json,
        run_dir=str(run_dir),
        meta=meta,
    )
    report_path.write_text(html, encoding="utf-8")
    return report_path
