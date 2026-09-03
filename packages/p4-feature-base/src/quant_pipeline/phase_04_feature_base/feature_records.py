from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .artifact_protocol import lineage_hash
from .economic_models import AtomicFeatureRecord, MissingnessState, ObserverSpec, QualityState
from .provenance import Provenance


def records_from_series(
    *,
    entity_id: str,
    series: pd.Series,
    spec: ObserverSpec,
    unit: str,
    provenance_by_time: Mapping[datetime, Provenance | None],
    attributes: dict[str, Any] | None = None,
) -> list[AtomicFeatureRecord]:
    output: list[AtomicFeatureRecord] = []
    for decision_time, raw_value in series.items():
        provenance = provenance_by_time.get(decision_time)
        if provenance is None:
            continue
        value = None if pd.isna(raw_value) or not np.isfinite(float(raw_value)) else float(raw_value)
        missingness = MissingnessState.OBSERVED if value is not None else MissingnessState.STRUCTURALLY_MISSING
        quality = provenance.quality_state if value is not None else QualityState.DEGRADED
        output.append(
            AtomicFeatureRecord(
                decision_time=decision_time,
                entity_id=entity_id,
                feature_id=spec.feature_id,
                observer_id=spec.observer_id,
                parameterization_id=spec.parameterization_id,
                horizon_group=spec.horizon_group,
                value=value,
                unit=unit,
                available_at=provenance.available_at,
                source_modalities=provenance.modalities,
                quality_state=quality,
                missingness_state=missingness,
                record_lineage_id=lineage_hash(provenance.lineage_ids),
                attributes=attributes or {},
            )
        )
    return output


def one_record(
    *,
    decision_time: datetime,
    entity_id: str,
    spec: ObserverSpec,
    value: float | None,
    unit: str,
    available_at: datetime,
    lineage_ids: Iterable[str],
    modalities: Iterable[str],
    attributes: dict[str, Any] | None = None,
    quality_state: QualityState = QualityState.PASS,
    missingness_state: MissingnessState | None = None,
) -> AtomicFeatureRecord:
    resolved_missingness = missingness_state or (
        MissingnessState.OBSERVED if value is not None else MissingnessState.STRUCTURALLY_MISSING
    )
    resolved_quality = quality_state if value is not None else QualityState.DEGRADED
    return AtomicFeatureRecord(
        decision_time=decision_time,
        entity_id=entity_id,
        feature_id=spec.feature_id,
        observer_id=spec.observer_id,
        parameterization_id=spec.parameterization_id,
        horizon_group=spec.horizon_group,
        value=value,
        unit=unit,
        available_at=available_at,
        source_modalities=tuple(sorted(set(modalities))),
        quality_state=resolved_quality,
        missingness_state=resolved_missingness,
        record_lineage_id=lineage_hash(lineage_ids),
        attributes=attributes or {},
    )
