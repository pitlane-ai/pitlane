"""Generate JSON Schema and docs for the eval YAML format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pitlane.config import EvalConfig


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def generate_json_schema() -> dict:
    return EvalConfig.model_json_schema()


def write_json_schema(path: Path) -> None:
    _ensure_parent(path)
    schema = generate_json_schema()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True))


def _format_fields(fields: Iterable[str]) -> str:
    return ", ".join(fields)


def generate_schema_doc() -> str:
    schema = generate_json_schema()
    defs = schema.get("$defs", {})

    assertion_models = [
        "FileExistsAssertion",
        "FileContainsAssertion",
        "CommandSucceedsAssertion",
        "CommandFailsAssertion",
        "BleuAssertion",
        "RougeAssertion",
        "BERTScoreAssertion",
        "CosineSimilarityAssertion",
    ]

    lines: list[str] = []
    lines.append("# pitlane YAML Schema")
    lines.append("")
    lines.append("This doc is generated from the Pydantic models.")
    lines.append("")
    lines.append("## Top-level keys")
    lines.append("- `assistants`: mapping of assistant names to config.")
    lines.append("- `tasks`: list of task definitions.")
    lines.append("")
    lines.append("## Assistant Config")
    lines.append(
        "- `type`: string (required) - one of: bob, claude-code, mistral-vibe, opencode"
    )
    lines.append("- `args`: object (optional) - assistant-specific arguments")
    lines.append("- `skills`: array (optional) - list of skill references")
    lines.append("")
    lines.append("## Assertions")
    for model_name in assertion_models:
        model_def = defs.get(model_name, {})
        props = model_def.get("properties", {})
        prop_keys = list(props.keys())
        if not prop_keys:
            continue
        top_key = prop_keys[0]
        if top_key == "file_contains":
            spec = defs.get("FileContainsSpec", {})
            spec_fields = spec.get("properties", {}).keys()
            lines.append(f"- `{top_key}`: {{ {_format_fields(spec_fields)} }}")
        elif top_key in {"bleu", "rouge", "bertscore", "cosine_similarity"}:
            spec = defs.get("SimilaritySpec", {})
            spec_fields = spec.get("properties", {}).keys()
            lines.append(f"- `{top_key}`: {{ {_format_fields(spec_fields)} }}")
        else:
            lines.append(f"- `{top_key}`: string")

    lines.append("")
    return "\n".join(lines)


def write_schema_doc(path: Path) -> None:
    _ensure_parent(path)
    path.write_text(generate_schema_doc())
