from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import numpy as np
from .artifacts import ArtifactEnvelope
from .errors import S8Error

@dataclass(frozen=True)
class GroupMatrix:
    family_id: str
    horizon_group: str
    feature_ids: tuple[str, ...]
    modalities: dict[str, tuple[int, ...]]
    times: tuple[datetime, ...]
    entities: tuple[str, ...]
    values: np.ndarray
    observed: np.ndarray
    row_keys: tuple[tuple[datetime, str], ...]
    available_at: tuple[datetime, ...]


def _catalog(matrix: ArtifactEnvelope) -> dict[str, dict[str, Any]]:
    catalog = matrix.metadata.get("feature_catalog")
    if not isinstance(catalog, dict) or not catalog:
        raise S8Error("P4_S8_FEATURE_CATALOG_MISSING", "selected matrix metadata.feature_catalog is required")
    return catalog


def build_group_matrices(matrix: ArtifactEnvelope) -> list[GroupMatrix]:
    catalog = _catalog(matrix)
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    feature_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for item in catalog.values():
        key = (str(item["family_id"]), str(item["horizon_group"]))
        groups[key].append(str(item["feature_id"]))
        feature_meta[(str(item["horizon_group"]), str(item["feature_id"]))] = item
    records_by_horizon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in matrix.records:
        records_by_horizon[str(record["horizon_group"])].append(record)
    output: list[GroupMatrix] = []
    for (family, horizon), features in sorted(groups.items()):
        rows = sorted(records_by_horizon.get(horizon, []), key=lambda r: (r["decision_time"], r["entity_id"]))
        if not rows:
            continue
        feature_ids = tuple(sorted(features))
        values = np.full((len(rows), len(feature_ids)), np.nan, dtype=float)
        observed = np.zeros_like(values, dtype=bool)
        for i, record in enumerate(rows):
            selected = record.get("values", {})
            missing = record.get("missingness_mask", {})
            for j, feature in enumerate(feature_ids):
                value = selected.get(feature)
                is_missing = bool(missing.get(feature, value is None))
                if value is not None and not is_missing:
                    values[i, j] = float(value)
                    observed[i, j] = True
        modality_indices: dict[str, list[int]] = defaultdict(list)
        for j, feature in enumerate(feature_ids):
            meta = feature_meta[(horizon, feature)]
            modalities = meta.get("source_modalities") or ["unknown"]
            modality_indices[str(sorted(modalities)[0])].append(j)
        keys = tuple((datetime.fromisoformat(str(r["decision_time"]).replace("Z", "+00:00")), str(r["entity_id"])) for r in rows)
        available_at = tuple(
            datetime.fromisoformat(str(r["available_at"]).replace("Z", "+00:00"))
            for r in rows
        )
        output.append(GroupMatrix(family, horizon, feature_ids,
            {key: tuple(value) for key, value in sorted(modality_indices.items())},
            tuple(sorted({key[0] for key in keys})), tuple(sorted({key[1] for key in keys})),
            values, observed, keys, available_at))
    return output


def impute_from_train(train: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Median-impute from the training slice without emitting all-NaN warnings.

    Entirely unobserved columns receive a neutral placeholder here, but callers must remove
    those columns before fitting a representation. Keeping that responsibility explicit
    prevents a placeholder from being mistaken for observed information.
    """
    medians = np.zeros(train.shape[1], dtype=float)
    for column in range(train.shape[1]):
        observed = train[np.isfinite(train[:, column]), column]
        if observed.size:
            medians[column] = float(np.median(observed))
    return np.where(np.isfinite(target), target, medians), medians
