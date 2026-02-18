from __future__ import annotations

from pathlib import Path
from typing import Any

from junitparser import TestCase, TestSuite, JUnitXml, Failure


def write_junit(run_dir: Path, all_results: dict[str, dict[str, Any]]) -> Path:
    """Write junit.xml from aggregated results dict, return path."""
    xml = JUnitXml()

    for assistant_name, assistant_results in all_results.items():
        for task_name, task_result in assistant_results.items():
            metrics = task_result.get("metrics", {})
            assertions = task_result.get("assertions", [])
            metrics_stats = task_result.get("metrics_stats", {})

            failures = sum(1 for a in assertions if not a.get("passed", True))

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
    from jinja2 import Environment, FileSystemLoader
    from junitparser import JUnitXml

    junit_path = run_dir / "junit.xml"
    report_path = run_dir / "report.html"

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
            }
        )

    total_tests = sum(s["tests"] for s in suites)
    total_failures = sum(s["failures"] for s in suites)
    total_errors = sum(s["errors"] for s in suites)

    tmpl_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)), autoescape=True)
    template = env.get_template("report.html.j2")

    html = template.render(
        suites=suites,
        total_tests=total_tests,
        total_failures=total_failures,
        total_errors=total_errors,
        run_dir=str(run_dir),
    )
    report_path.write_text(html, encoding="utf-8")
    return report_path
