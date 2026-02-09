from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_eval.adapters import get_adapter
from agent_eval.adapters.base import AdapterResult, BaseAdapter
from agent_eval.assertions.deterministic import evaluate_assertion
from agent_eval.assertions.base import AssertionResult
from agent_eval.config import EvalConfig, AssistantConfig, TaskConfig
from agent_eval.metrics import collect_metrics
from agent_eval.workspace import WorkspaceManager


class Runner:
    """Orchestrates evaluation runs."""

    def __init__(
        self,
        config: EvalConfig,
        output_dir: Path,
        task_filter: str | None = None,
        assistant_filter: str | None = None,
    ):
        self.config = config
        self.output_dir = output_dir
        self.task_filter = task_filter
        self.assistant_filter = assistant_filter

    def execute(self) -> Path:
        """Run all tasks against all assistants. Returns the run directory."""
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        workspace_mgr = WorkspaceManager(base_dir=run_dir)
        all_results: dict[str, dict[str, Any]] = {}

        tasks = self.config.tasks
        if self.task_filter:
            tasks = [t for t in tasks if t.name == self.task_filter]

        assistants = self.config.assistants
        if self.assistant_filter:
            assistants = {
                k: v for k, v in assistants.items()
                if k == self.assistant_filter
            }

        for assistant_name, assistant_config in assistants.items():
            all_results[assistant_name] = {}
            adapter = get_adapter(assistant_config.adapter)

            for task in tasks:
                result = self._run_task(
                    workspace_mgr=workspace_mgr,
                    adapter=adapter,
                    assistant_name=assistant_name,
                    assistant_config=assistant_config,
                    task=task,
                    run_id=run_id,
                )
                all_results[assistant_name][task.name] = result

        # Write results
        (run_dir / "results.json").write_text(
            json.dumps(all_results, indent=2, default=str)
        )

        # Write metadata
        meta = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assistants": list(assistants.keys()),
            "tasks": [t.name for t in tasks],
        }
        (run_dir / "meta.yaml").write_text(yaml.dump(meta, default_flow_style=False))

        return run_dir

    def _run_task(
        self,
        workspace_mgr: WorkspaceManager,
        adapter: BaseAdapter,
        assistant_name: str,
        assistant_config: AssistantConfig,
        task: TaskConfig,
        run_id: str,
    ) -> dict[str, Any]:
        """Run a single task for a single assistant."""
        source_dir = Path(task.workdir)
        workspace = workspace_mgr.create_workspace(
            source_dir=source_dir,
            run_id=".",  # already inside run_dir
            assistant_name=assistant_name,
            task_name=task.name,
        )

        # Snapshot files before
        files_before = {
            str(f.relative_to(workspace))
            for f in workspace.rglob("*")
            if f.is_file()
        }

        # Install skills
        for skill in assistant_config.skills:
            workspace_mgr.install_skill(
                workspace=workspace,
                skill=skill,
                agent_type=adapter.agent_type(),
            )

        # Run adapter
        config = {**assistant_config.args, "timeout": task.timeout}
        adapter_result = adapter.run(
            prompt=task.prompt,
            workdir=workspace,
            config=config,
        )

        # Evaluate assertions
        assertion_results = []
        for assertion_def in task.assertions:
            ar = evaluate_assertion(workspace, assertion_def)
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

        return {
            "metrics": metrics,
            "assertions": [
                {"name": ar.name, "passed": ar.passed, "message": ar.message}
                for ar in assertion_results
            ],
            "all_passed": all(ar.passed for ar in assertion_results),
        }
