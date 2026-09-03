from __future__ import annotations

from collections.abc import Iterable

from .domain.canonical import digest

FEATURE_NAMES: tuple[str, ...] = (
    "cost_quality",
    "edge_signal",
    "risk_penalty",
    "robustness",
)
FEATURE_SCHEMA_VERSION = "2.3.2"


def canonical_feature_names(names: Iterable[str] = FEATURE_NAMES) -> tuple[str, ...]:
    values = tuple(sorted({str(name) for name in names}))
    if not values:
        raise ValueError("feature schema cannot be empty")
    return values


def feature_schema_hash(names: Iterable[str] = FEATURE_NAMES) -> str:
    return digest(list(canonical_feature_names(names)))
