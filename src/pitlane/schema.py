"""Generate JSON Schema and docs for the eval YAML format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pitlane.config import EvalConfig


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _collect_refs(obj: object) -> set[str]:
    """Return all ``$defs`` names referenced via ``$ref`` inside *obj*."""
    refs: set[str] = set()
    if isinstance(obj, dict):
        if "$ref" in obj:
            ref = obj["$ref"]
            if ref.startswith("#/$defs/"):
                refs.add(ref.removeprefix("#/$defs/"))
        for v in obj.values():
            refs |= _collect_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            refs |= _collect_refs(v)
    return refs


def _order_defs(defs: dict) -> dict:
    """Topologically sort ``$defs`` so referenced types precede referencing types."""
    ordered: dict[str, dict] = {}
    visited: set[str] = set()

    def _visit(name: str) -> None:
        if name in visited or name not in defs:
            return
        visited.add(name)
        for dep in _collect_refs(defs[name]):
            _visit(dep)
        ordered[name] = defs[name]

    for name in defs:
        _visit(name)
    return ordered


def generate_json_schema() -> dict:
    schema = EvalConfig.model_json_schema()
    if "$defs" in schema:
        schema["$defs"] = _order_defs(schema["$defs"])
    return schema


def write_json_schema(path: Path) -> None:
    _ensure_parent(path)
    schema = generate_json_schema()
    path.write_text(json.dumps(schema, indent=2) + "\n")


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
