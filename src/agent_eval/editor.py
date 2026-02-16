from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

YAML_SCHEMA_TARGETS = [
    "eval.yaml",
    "examples/*.yaml",
    "**/*eval*.y*ml",
]


@dataclass(frozen=True)
class SettingsUpdatePlan:
    original: dict[str, Any]
    updated: dict[str, Any]
    preview_lines: list[str]
    changed: bool


def load_vscode_settings(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return {}, False

    raw = path.read_text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")
    return data, True


def plan_vscode_settings_update(
    settings: dict[str, Any], schema_ref: str
) -> SettingsUpdatePlan:
    updated = dict(settings)

    yaml_schemas_obj = updated.get("yaml.schemas", {})
    if yaml_schemas_obj is None:
        yaml_schemas_obj = {}
    if not isinstance(yaml_schemas_obj, dict):
        raise ValueError("Expected `yaml.schemas` to be a JSON object when present")

    yaml_schemas = dict(yaml_schemas_obj)
    old_schema_targets = yaml_schemas.get(schema_ref)
    old_validate = updated.get("yaml.validate")

    yaml_schemas[schema_ref] = list(YAML_SCHEMA_TARGETS)
    updated["yaml.schemas"] = yaml_schemas
    updated["yaml.validate"] = True

    preview_lines = [
        "Planned updates to VS Code settings:",
        f"- `yaml.schemas[{schema_ref!r}]` -> {YAML_SCHEMA_TARGETS}",
        "- `yaml.validate` -> true",
    ]
    if old_schema_targets is not None:
        preview_lines.append(
            f"- Previous `yaml.schemas[{schema_ref!r}]`: {old_schema_targets}"
        )
    if old_validate is not None:
        preview_lines.append(f"- Previous `yaml.validate`: {old_validate}")

    return SettingsUpdatePlan(
        original=settings,
        updated=updated,
        preview_lines=preview_lines,
        changed=(settings != updated),
    )


def default_backup_path(settings_path: Path, now: datetime | None = None) -> Path:
    ts = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return Path(f"{settings_path}.bak.{ts}")


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        encoding="utf-8",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")

    try:
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def create_backup(source: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_path)
