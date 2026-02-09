from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def generate_report(run_dir: Path) -> Path:
    """Generate a self-contained HTML report from run results."""
    results_file = run_dir / "results.json"
    results = json.loads(results_file.read_text())

    assistants = list(results.keys())
    tasks = []
    for assistant_results in results.values():
        for task_name in assistant_results:
            if task_name not in tasks:
                tasks.append(task_name)

    metric_keys = [
        "wall_clock_seconds", "exit_code", "files_created", "files_modified",
        "total_lines_generated", "token_usage_input", "token_usage_output",
        "cost_usd", "tool_calls_count", "assertion_pass_count",
        "assertion_fail_count", "assertion_pass_rate",
    ]

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    template = env.get_template("report.html.j2")

    html = template.render(
        assistants=assistants,
        tasks=tasks,
        results=results,
        metric_keys=metric_keys,
    )

    report_path = run_dir / "report.html"
    report_path.write_text(html)
    return report_path
