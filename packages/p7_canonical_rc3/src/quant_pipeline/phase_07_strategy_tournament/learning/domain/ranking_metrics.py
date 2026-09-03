from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Mapping

import numpy as np


def _order(scores: np.ndarray, candidate_ids: list[str]) -> np.ndarray:
    return np.array(sorted(range(len(scores)), key=lambda i: (-float(scores[i]), candidate_ids[i])), dtype=int)


def _rank_relevance(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    relevance = np.empty(len(values), dtype=float)
    relevance[order] = np.arange(len(values), dtype=float)
    return relevance


def ndcg_at_k(values: np.ndarray, scores: np.ndarray, candidate_ids: list[str], k: int) -> float:
    if len(values) < 2:
        return 1.0
    relevance = _rank_relevance(values)
    predicted = _order(scores, candidate_ids)[: min(k, len(values))]
    ideal = np.argsort(-relevance, kind="mergesort")[: min(k, len(values))]

    def dcg(indices: np.ndarray) -> float:
        return float(sum((2.0 ** relevance[idx] - 1.0) / math.log2(pos + 2.0) for pos, idx in enumerate(indices)))

    ideal_value = dcg(ideal)
    return 1.0 if ideal_value == 0.0 else dcg(predicted) / ideal_value


def precision_at_k(values: np.ndarray, scores: np.ndarray, candidate_ids: list[str], k: int) -> float:
    size = min(k, len(values))
    predicted = set(_order(scores, candidate_ids)[:size].tolist())
    truth = set(np.argsort(-values, kind="mergesort")[:size].tolist())
    return len(predicted & truth) / size if size else 1.0


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average = (start + end - 1) / 2.0
        ranks[order[start:end]] = average
        start = end
    return ranks


def spearman(values: np.ndarray, scores: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    left = _average_ranks(values)
    right = _average_ranks(scores)
    left -= left.mean()
    right -= right.mean()
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return 0.0 if denominator == 0.0 else float(left @ right / denominator)


def regret_at_k(values: np.ndarray, scores: np.ndarray, candidate_ids: list[str], k: int) -> float:
    selected = _order(scores, candidate_ids)[: min(k, len(values))]
    return float(np.max(values) - np.max(values[selected]))


def top_bottom_spread(values: np.ndarray, scores: np.ndarray, candidate_ids: list[str], k: int) -> float:
    size = min(k, max(1, len(values) // 2))
    order = _order(scores, candidate_ids)
    return float(np.mean(values[order[:size]]) - np.mean(values[order[-size:]]))


def metrics_by_query(records: Iterable[Mapping[str, object]], *, score_field: str, k: int) -> list[dict[str, float | str | int]]:
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in records:
        groups[str(record["query_id"])].append(record)
    result: list[dict[str, float | str | int]] = []
    for query_id in sorted(groups):
        rows = sorted(groups[query_id], key=lambda row: str(row["candidate_id"]))
        values = np.array([float(row["utility_label"]) for row in rows], dtype=float)
        scores = np.array([float(row[score_field]) for row in rows], dtype=float)
        candidate_ids = [str(row["candidate_id"]) for row in rows]
        result.append(
            {
                "query_id": query_id,
                "candidate_count": len(rows),
                "ndcg_at_k": ndcg_at_k(values, scores, candidate_ids, k),
                "precision_at_k": precision_at_k(values, scores, candidate_ids, k),
                "spearman": spearman(values, scores),
                "regret_at_k": regret_at_k(values, scores, candidate_ids, k),
                "top_bottom_spread": top_bottom_spread(values, scores, candidate_ids, k),
            }
        )
    return result


def aggregate_metrics(rows: list[Mapping[str, float | str | int]]) -> dict[str, float]:
    fields = ("ndcg_at_k", "precision_at_k", "spearman", "regret_at_k", "top_bottom_spread")
    if not rows:
        return {field: 0.0 for field in fields}
    return {field: float(np.mean([float(row[field]) for row in rows])) for field in fields}
