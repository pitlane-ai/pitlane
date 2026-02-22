"""Similarity-based assertion checks (BLEU, ROUGE, BERTScore, cosine)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitlane.assertions.base import AssertionResult

for _name in ("huggingface_hub", "transformers", "sentence_transformers", "evaluate", "filelock"):
    logging.getLogger(_name).setLevel(logging.ERROR)


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
    workdir: str | Path,
    kind: str,
    spec: dict[str, Any],
    *,
    source_dir: str | Path | None = None,
    logger: logging.Logger,
) -> AssertionResult:
    logger.info(
        f"Evaluating {kind} similarity: {spec.get('actual')} vs {spec.get('expected')}"
    )

    actual_path = spec["actual"]
    try:
        actual_text = _read_text(workdir, actual_path)
    except FileNotFoundError:
        logger.warning(f"File {actual_path} not found")
        return AssertionResult(
            name=f"{kind}:{actual_path}:{spec['expected']}",
            passed=False,
            message=f"{actual_path} not found",
            score=0.0,
        )
    # Read expected files from original source_dir (not workspace) so that
    # reference files don't need to be copied into the AI-visible workspace.
    expected_base = Path(source_dir) if source_dir else Path(workdir)
    expected_text = _read_text(expected_base, spec["expected"])
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

    logger.info(f"{kind} score: {score:.4f}, min_score: {min_score}, passed={passed}")

    message = f"score={score:.4f}"
    if min_score is not None:
        message = f"{message} min_score={min_score:.4f}"

    # Normalize score for weighted grade computation.
    # With min_score: scale so that meeting the threshold = 1.0 and below
    # scales proportionally (e.g. 0.35 vs threshold 0.7 → 0.5).
    # Without min_score: use raw score (observational).
    if min_score is not None and min_score > 0:
        normalized = min(score / min_score, 1.0)
    else:
        normalized = score

    return AssertionResult(
        name=f"{kind}:{spec['actual']}:{spec['expected']}",
        passed=passed,
        message=message,
        score=normalized,
    )
