"""Similarity-based assertion checks (BLEU, ROUGE, BERTScore, cosine)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_eval.assertions.base import AssertionResult


def _require_similarity_deps() -> None:
    try:
        import evaluate  # noqa: F401
        import sentence_transformers  # noqa: F401
        import bert_score  # noqa: F401
    except Exception as exc:  # pragma: no cover - import errors vary by environment
        raise ValueError(
            "Similarity assertions require optional deps. Install with: uv pip install '.[similarity]'"
        ) from exc


def _read_text(workdir: str | Path, relpath: str) -> str:
    path = Path(workdir) / relpath
    return path.read_text()


def _score_bleu(actual: str, expected: str) -> float:
    import evaluate

    metric = evaluate.load("bleu")
    result = metric.compute(predictions=[actual], references=[[expected]])
    return float(result["bleu"])


def _score_rouge(actual: str, expected: str, metric: str | None) -> float:
    import evaluate

    metric_name = metric or "rougeL"
    rouge = evaluate.load("rouge")
    result = rouge.compute(predictions=[actual], references=[expected])
    if metric_name not in result:
        raise ValueError(f"Unknown ROUGE metric '{metric_name}'")
    return float(result[metric_name])


def _score_bertscore(actual: str, expected: str, metric: str | None) -> float:
    import evaluate

    metric_name = metric or "f1"
    bert = evaluate.load("bertscore")
    result = bert.compute(predictions=[actual], references=[expected], lang="en")
    if metric_name not in result:
        raise ValueError(f"Unknown BERTScore metric '{metric_name}'")
    score_list = result[metric_name]
    return float(score_list[0])


def _score_cosine(actual: str, expected: str) -> float:
    from sentence_transformers import SentenceTransformer, util

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode([actual, expected], normalize_embeddings=True)
    score = util.cos_sim(embeddings[0], embeddings[1])
    return float(score.item())


def evaluate_similarity_assertion(
    workdir: str | Path, kind: str, spec: dict[str, Any]
) -> AssertionResult:
    _require_similarity_deps()

    actual_text = _read_text(workdir, spec["actual"])
    expected_text = _read_text(workdir, spec["expected"])
    metric = spec.get("metric")
    min_score = spec.get("min_score")

    if kind == "bleu":
        score = _score_bleu(actual_text, expected_text)
    elif kind == "rouge":
        score = _score_rouge(actual_text, expected_text, metric)
    elif kind == "bertscore":
        score = _score_bertscore(actual_text, expected_text, metric)
    elif kind == "cosine_similarity":
        score = _score_cosine(actual_text, expected_text)
    else:
        raise ValueError(f"Unknown similarity assertion type: '{kind}'")

    passed = True if min_score is None else score >= min_score
    message = f"score={score:.4f}"
    if min_score is not None:
        message = f"{message} min_score={min_score:.4f}"

    return AssertionResult(
        name=f"{kind}:{spec['actual']}:{spec['expected']}",
        passed=passed,
        message=message,
    )
