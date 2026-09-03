from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.canonical import (
    normalize_text,
    tokenize,
)


def canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return canonicalize(value.model_dump(mode="json"))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(key): canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    constant: int,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (constant + rank)
    return scores


def lexical_similarity(left: str, right: str) -> float:
    return float(SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio())


def min_max_normalize(scores: Mapping[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    minimum = min(scores.values())
    maximum = max(scores.values())
    if math.isclose(minimum, maximum):
        return {key: 1.0 if maximum > 0 else 0.0 for key in scores}
    scale = maximum - minimum
    return {key: (value - minimum) / scale for key, value in scores.items()}


def unique_preserving_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return tuple(output)


__all__ = [
    "canonical_json",
    "content_hash",
    "lexical_similarity",
    "min_max_normalize",
    "normalize_text",
    "reciprocal_rank_fusion",
    "sha256_bytes",
    "tokenize",
    "unique_preserving_order",
]
