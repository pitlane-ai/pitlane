from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from pitlane.adapters import get_adapter
from pitlane.adapters.base import BaseAdapter
from pitlane.assertions.deterministic import evaluate_assertion
from pitlane.config import EvalConfig, AssistantConfig, TaskConfig
from pitlane.metrics import (
    collect_metrics,
    aggregate_results,
)
from pitlane.verbose import setup_logger
from pitlane.workspace import WorkspaceManager, validate_mcp_env

AssistantName = str
TaskName = str


@dataclass
class IterationResult:
    metrics: dict[str, float | None]
    assertions: list[dict[str, Any]]
    all_passed: bool
    iteration_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Runner:
    """Orchestrates evaluation runs."""

    def __init__(
        self,
        config: EvalConfig,
        output_dir: Path,
        task_filter: str | None = None,
        assistant_filter: str | None = None,
        verbose: bool = False,
        parallel_tasks: int = 1,
        repeat: int = 1,
    ):
        self.config = config
        self.output_dir = output_dir
        self.task_filter = task_filter
        self.assistant_filter = assistant_filter
        self.verbose = verbose
        self.parallel_tasks = parallel_tasks
        self.repeat = repeat
        self.interrupted = False

    def execute(self) -> Path:
        """Run all tasks against all assistants. Returns the run directory."""
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Setup main logger for high-level messages only
        debug_file = run_dir / "debug.log"
        logger = setup_logger(
            debug_file, verbose=self.verbose, logger_name="pitlane_main"
        )
        logger.debug("Starting evaluation run")

        workspace_mgr = WorkspaceManager(base_dir=run_dir)
        all_results: dict[str, dict[str, Any]] = {}

        tasks = self.config.tasks
        if self.task_filter:
            tasks = [t for t in tasks if t.name == self.task_filter]

        assistants = self.config.assistants
        if self.assistant_filter:
            assistants = {
                k: v for k, v in assistants.items() if k == self.assistant_filter
            }

        validate_mcp_env(assistants)

        cli_versions = {}
        for assistant_name, assistant_config in assistants.items():
            adapter = get_adapter(assistant_config.adapter)
            version = adapter.get_cli_version()
            if version:
                cli_versions[f"{assistant_name} ({adapter.cli_name()})"] = version

        total_tasks = len(assistants) * len(tasks) * self.repeat
        print(
            f"Running {total_tasks} task(s) with parallelism {self.parallel_tasks}..."
        )

        with ThreadPoolExecutor(max_workers=self.parallel_tasks) as executor:
            future_to_task = {}

            for assistant_name, assistant_config in assistants.items():
                all_results[assistant_name] = {}
                adapter = get_adapter(assistant_config.adapter)

                for task in tasks:
                    for iteration in range(self.repeat):
                        future = executor.submit(
                            self._run_task,
                            workspace_mgr=workspace_mgr,
                            adapter=adapter,
                            assistant_name=assistant_name,
                            assistant_config=assistant_config,
                            task=task,
                            logger=logger,
                            iteration=iteration,
                        )
                        future_to_task[future] = (assistant_name, task.name, iteration)

            # Collect per-iteration results
            iteration_results: dict[
                AssistantName, dict[TaskName, list[IterationResult]]
            ] = {}
            for assistant_name in assistants:
                iteration_results[assistant_name] = {}

            completed_count = 0
            try:
                for future in as_completed(future_to_task):
                    assistant_name, task_name, iteration = future_to_task[future]
                    try:
                        result_dict = future.result()

                        completed_count += 1
                        status = "PASS" if result_dict["all_passed"] else "FAIL"
                        n_passed = sum(
                            1 for a in result_dict["assertions"] if a["passed"]
                        )
                        n_total = len(result_dict["assertions"])
                        duration = result_dict["metrics"].get("wall_clock_seconds")
                        dur = f", {duration:.0f}s" if duration is not None else ""
                        label = f"{assistant_name} / {task_name}"
                        if self.repeat > 1:
                            label += f" iter-{iteration}"
                        print(
                            f"  [{completed_count}/{len(future_to_task)}] {status}  {label} ({n_passed}/{n_total} assertions{dur})"
                        )

                        # Convert dict to IterationResult object
                        result = IterationResult(
                            metrics=result_dict["metrics"],
                            assertions=result_dict["assertions"],
                            all_passed=result_dict["all_passed"],
                            iteration_index=iteration,
                        )
                        if task_name not in iteration_results[assistant_name]:
                            iteration_results[assistant_name][task_name] = []
                        iteration_results[assistant_name][task_name].append(result)
                    except Exception as e:
                        completed_count += 1
                        label = f"{assistant_name} / {task_name}"
                        if self.repeat > 1:
                            label += f" iter-{iteration}"
                        print(
                            f"  [{completed_count}/{len(future_to_task)}] ERROR  {label}: {e}"
                        )
                        logger.error(
                            f"Task '{task_name}' failed for assistant '{assistant_name}': {e}"
                        )
                        raise
            except KeyboardInterrupt:
                self.interrupted = True
                logger.warning(
                    "Run interrupted by user (Ctrl+C). Cancelling pending tasks, and saving partial results..."
                )

                cancelled_count = 0
                for future in future_to_task:
                    # this only cancels tasks not yet started
                    if future.cancel():
                        cancelled_count += 1

                logger.info(
                    f"Cancelled {cancelled_count} pending task(s). Running tasks will complete naturally."
                )
                logger.info(
                    "Waiting for running tasks to finish (this may take up to their timeout duration)..."
                )

                # Collect results from any futures that completed
                for future, (
                    assistant_name,
                    task_name,
                    iteration,
                ) in future_to_task.items():
                    if task_name not in iteration_results[assistant_name]:
                        iteration_results[assistant_name][task_name] = []
                    if future.done() and not future.cancelled():
                        try:
                            result_dict = future.result(timeout=0)
                            result = IterationResult(
                                metrics=result_dict["metrics"],
                                assertions=result_dict["assertions"],
                                all_passed=result_dict["all_passed"],
                                iteration_index=iteration,
                            )
                            # Only add if not already collected
                            if not any(
                                r.iteration_index == iteration
                                for r in iteration_results[assistant_name][task_name]
                            ):
                                iteration_results[assistant_name][task_name].append(
                                    result
                                )
                        except Exception as e:
                            logger.debug(
                                f"Failed to collect result for {assistant_name}/{task_name}: {e}"
                            )

        # Build final results: always aggregate (single run is just 1 iteration)
        for assistant_name in iteration_results:
            for task_name in iteration_results[assistant_name]:
                results_list = iteration_results[assistant_name][task_name]
                # Skip tasks with no completed results (can happen during interrupts)
                if not results_list:
                    continue
                results_list.sort(key=lambda r: r.iteration_index)
                aggregated = aggregate_results(results_list)
                all_results[assistant_name][task_name] = aggregated.to_dict()

        self._write_results(run_dir, all_results, assistants, tasks, cli_versions)

        return run_dir

    def _write_results(
        self,
        run_dir: Path,
        all_results: dict[str, dict[str, Any]],
        assistants: dict[str, AssistantConfig],
        tasks: list[TaskConfig],
        cli_versions: dict[str, str],
    ) -> None:
        """Write junit.xml and meta.yaml to the run directory."""
        from pitlane.reporting.junit import write_junit

        write_junit(run_dir, all_results)

        try:
            import importlib.metadata

            pitlane_version = importlib.metadata.version("pitlane")
        except Exception:
            pitlane_version = "unknown"

        meta: dict[str, Any] = {
            "run_id": run_dir.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assistants": list(assistants.keys()),
            "tasks": [t.name for t in tasks],
            "cli_versions": cli_versions,
            "pitlane_version": pitlane_version,
            "repeat": self.repeat,
        }
        if self.interrupted:
            meta["interrupted"] = True

        (run_dir / "meta.yaml").write_text(yaml.dump(meta, default_flow_style=False))

    def _run_task(
        self,
        workspace_mgr: WorkspaceManager,
        adapter: BaseAdapter,
        assistant_name: str,
        assistant_config: AssistantConfig,
        task: TaskConfig,
        logger: logging.Logger,
        iteration: int,
    ) -> dict[str, Any]:
        """Run a single task for a single assistant."""

        source_dir = Path(task.workdir)
        task_name_with_iter = f"{task.name}/iter-{iteration}"
        workspace = workspace_mgr.create_workspace(
            source_dir=source_dir,
            run_id=".",  # already inside run_dir
            assistant_name=assistant_name,
            task_name=task_name_with_iter,
        )

        # task-specific debug log
        task_dir = workspace.parent  # task dir
        task_debug_file = task_dir / "debug.log"

        # note: logger name must be unique per assistant+task+iteration to avoid handler collision
        task_logger = setup_logger(
            debug_file=task_debug_file,
            verbose=self.verbose,
            logger_name=f"pitlane_{assistant_name}_{task.name}_iter{iteration}",
        )

        logger.debug(f"Running task '{task.name}' with assistant '{assistant_name}'")

        # Snapshot files before
        files_before = {
            str(f.relative_to(workspace)) for f in workspace.rglob("*") if f.is_file()
        }

        # Log CLI version information
        cli_version = adapter.get_cli_version()
        if cli_version:
            task_logger.debug(f"Using {adapter.cli_name()} CLI version: {cli_version}")
        else:
            task_logger.debug(f"Could not detect {adapter.cli_name()} CLI version")

        for skill in assistant_config.skills:
            workspace_mgr.install_skill(
                workspace=workspace,
                skill=skill,
                agent_type=adapter.agent_type(),
            )

        for mcp in assistant_config.mcps:
            adapter.install_mcp(workspace=workspace, mcp=mcp)

        config = {**assistant_config.args, "timeout": task.timeout}
        adapter_result = adapter.run(
            prompt=task.prompt,
            workdir=workspace,
            config=config,
            logger=task_logger,
        )

        # Evaluate assertions
        assertion_results = []
        for assertion_def in task.assertions:
            ar = evaluate_assertion(
                workspace, assertion_def, source_dir=source_dir, logger=task_logger
            )
            assertion_results.append(ar)

        # Collect metrics
        metrics = collect_metrics(
            adapter_result=adapter_result,
            assertion_results=assertion_results,
            workspace=workspace,
            files_before=files_before,
        )

        # Save conversation log
        conv_dir = workspace.parent
        conv_file = conv_dir / "conversation.json"
        conv_file.write_text(
            json.dumps(adapter_result.conversation, indent=2, default=str)
        )

        logger.debug(
            f"Task '{task.name}' completed for assistant '{assistant_name}': "
            f"{sum(1 for ar in assertion_results if ar.passed)}/{len(assertion_results)} assertions passed"
        )
        task_logger.debug(
            f"Task '{task.name}' completed for assistant '{assistant_name}': "
            f"{sum(1 for ar in assertion_results if ar.passed)}/{len(assertion_results)} assertions passed"
        )

        return {
            "metrics": metrics,
            "assertions": [
                {
                    "name": ar.name,
                    "passed": ar.passed,
                    "message": ar.message,
                    "score": ar.score,
                    "weight": ar.weight,
                }
                for ar in assertion_results
            ],
            "all_passed": all(ar.passed for ar in assertion_results),
        }
