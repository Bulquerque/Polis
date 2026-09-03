from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

import pandas as pd

from .artifact_protocol import lineage_hash
from .economic_models import AtomicFeaturePanel, AtomicFeatureRecord, MissingnessState, QualityState


@dataclass(frozen=True)
class PerspectiveProvenance:
    available_at: datetime
    lineage_ids: tuple[str, ...]
    modalities: tuple[str, ...]
    feature_ids: tuple[str, ...]
    quality_state: QualityState


def combine_quality(states: Iterable[QualityState]) -> QualityState:
    values=set(states)
    if QualityState.BLOCKED in values:
        return QualityState.BLOCKED
    if QualityState.DEGRADED in values:
        return QualityState.DEGRADED
    return QualityState.PASS


class AtomicRecordIndex:
    def __init__(self, records: Iterable[AtomicFeatureRecord]) -> None:
        grouped: dict[tuple[str,str], list[AtomicFeatureRecord]]=defaultdict(list)
        for row in records:
            grouped[(row.entity_id,row.feature_id)].append(row)
        self._groups={}
        for key, values in grouped.items():
            ordered=tuple(sorted(values,key=lambda r:(r.decision_time,r.parameterization_id)))
            times=[r.decision_time for r in ordered if r.value is not None and r.quality_state is not QualityState.BLOCKED]
            if len(times)!=len(set(times)):
                raise ValueError(f"ambiguous atomic feature parameterizations for {key[0]}:{key[1]}")
            self._groups[key]=ordered

    def series(self, entity_id: str, feature_id: str) -> pd.Series:
        rows=self._groups.get((entity_id,feature_id),())
        values={r.decision_time:r.value for r in rows if r.value is not None and r.missingness_state is MissingnessState.OBSERVED}
        return pd.Series(values,dtype=float).sort_index()

    def entities(self, feature_id: str) -> tuple[str,...]:
        return tuple(sorted({entity for entity,feature in self._groups if feature==feature_id}))

    def features(self) -> tuple[str,...]:
        return tuple(sorted({feature for _,feature in self._groups}))

    def matching_features(self, prefix: str) -> tuple[str,...]:
        return tuple(feature for feature in self.features() if feature.startswith(prefix))

    def collect(self, *, entity_id: str, decision_time: datetime, requirements: Mapping[str,int]) -> PerspectiveProvenance | None:
        used=[]
        for feature_id,count in requirements.items():
            eligible=[r for r in self._groups.get((entity_id,feature_id),()) if r.decision_time<=decision_time and r.value is not None and r.quality_state is not QualityState.BLOCKED]
            if len(eligible)<count:
                return None
            used.extend(eligible[-count:])
        return _from_rows(used)

    def collect_many(self, requirements: Iterable[tuple[str,str,int]], decision_time: datetime) -> PerspectiveProvenance | None:
        used=[]
        for entity_id,feature_id,count in requirements:
            eligible=[r for r in self._groups.get((entity_id,feature_id),()) if r.decision_time<=decision_time and r.value is not None and r.quality_state is not QualityState.BLOCKED]
            if len(eligible)<count:
                return None
            used.extend(eligible[-count:])
        return _from_rows(used)


def _from_rows(rows: Iterable[AtomicFeatureRecord]) -> PerspectiveProvenance | None:
    items=tuple(rows)
    if not items:
        return None
    return PerspectiveProvenance(
        available_at=max(r.available_at for r in items),
        lineage_ids=tuple(sorted({r.record_lineage_id for r in items})),
        modalities=tuple(sorted({m for r in items for m in r.source_modalities})),
        feature_ids=tuple(sorted({r.feature_id for r in items})),
        quality_state=combine_quality(r.quality_state for r in items),
    )


def parse_atomic_panels(inputs: Mapping[str,object], names: tuple[str,...]) -> tuple[tuple[AtomicFeaturePanel,...], tuple[AtomicFeatureRecord,...]]:
    panels=[]
    records=[]
    for name in names:
        raw=inputs.get(name)
        if raw is None:
            continue
        panel=AtomicFeaturePanel.model_validate(raw)
        panels.append(panel)
        records.extend(panel.records)
    return tuple(panels),tuple(records)
