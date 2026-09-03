from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd

from .economic_errors import ContractError
from .economic_models import CanonicalObservation
from .provenance import is_usable


@dataclass(frozen=True)
class ObservationFrame:
    values: pd.DataFrame
    available_at: pd.Series
    lineage_ids: pd.Series
    modalities: pd.Series


def numeric_observations(
    observations: Iterable[CanonicalObservation],
    *,
    variable_prefixes: tuple[str, ...],
) -> list[CanonicalObservation]:
    selected: list[CanonicalObservation] = []
    for row in observations:
        if not row.variable_id.startswith(variable_prefixes):
            continue
        if not is_usable(row):
            continue
        if isinstance(row.value, bool) or not isinstance(row.value, (int, float)):
            continue
        if not pd.notna(row.value):
            continue
        selected.append(row)
    return selected


def build_numeric_wide(
    observations: Iterable[CanonicalObservation],
    *,
    variable_prefixes: tuple[str, ...],
) -> ObservationFrame:
    rows = numeric_observations(observations, variable_prefixes=variable_prefixes)
    records = [
        {
            "decision_time": row.decision_time,
            "entity_id": row.entity_id,
            "variable_id": row.variable_id,
            "value": float(row.value),
            "available_at": row.available_at,
            "record_lineage_id": row.record_lineage_id,
            "source_modality": row.source_modality,
        }
        for row in rows
    ]
    if not records:
        empty = pd.DataFrame(index=pd.MultiIndex.from_arrays([[], []], names=["decision_time", "entity_id"]))
        meta = pd.Series(dtype="object", index=empty.index)
        return ObservationFrame(empty, meta, meta, meta)
    frame = pd.DataFrame.from_records(records)
    duplicates = frame.duplicated(["decision_time", "entity_id", "variable_id"], keep=False)
    if duplicates.any():
        sample = frame.loc[duplicates, ["decision_time", "entity_id", "variable_id"]].head(20).to_dict("records")
        raise ContractError("P4_S4_DUPLICATE_OBSERVATION", "duplicate canonical observations", details={"sample": sample})
    values = frame.pivot(index=["decision_time", "entity_id"], columns="variable_id", values="value").sort_index()
    grouped = frame.groupby(["decision_time", "entity_id"], sort=True)
    available = grouped["available_at"].max().reindex(values.index)
    lineages = grouped["record_lineage_id"].agg(lambda items: tuple(sorted(set(items)))).reindex(values.index)
    modalities = grouped["source_modality"].agg(lambda items: tuple(sorted(set(items)))).reindex(values.index)
    return ObservationFrame(values, available, lineages, modalities)


def entity_groups(frame: pd.DataFrame) -> Iterable[tuple[str, pd.DataFrame]]:
    if frame.empty:
        return ()
    reset = frame.reset_index().sort_values(["entity_id", "decision_time"])
    return ((str(entity), group.set_index("decision_time").sort_index()) for entity, group in reset.groupby("entity_id", sort=True))


def max_available_at(values: Iterable[datetime]) -> datetime:
    return max(values)
