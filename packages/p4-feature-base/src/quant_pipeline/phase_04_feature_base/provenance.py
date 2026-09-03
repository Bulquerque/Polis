from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from .economic_models import CanonicalObservation, MissingnessState, QualityState


@dataclass(frozen=True)
class Provenance:
    available_at: datetime
    lineage_ids: tuple[str, ...]
    modalities: tuple[str, ...]
    quality_state: QualityState
    missingness_state: MissingnessState = MissingnessState.OBSERVED


def is_usable(row: CanonicalObservation) -> bool:
    return row.quality_state is not QualityState.BLOCKED and row.missingness_state is MissingnessState.OBSERVED


def combine_quality(states: Iterable[QualityState]) -> QualityState:
    values = tuple(states)
    if any(value is QualityState.BLOCKED for value in values):
        return QualityState.BLOCKED
    if any(value is QualityState.DEGRADED for value in values):
        return QualityState.DEGRADED
    return QualityState.PASS


def from_observations(rows: Iterable[CanonicalObservation]) -> Provenance | None:
    selected = tuple(row for row in rows if is_usable(row))
    if not selected:
        return None
    return Provenance(
        available_at=max(row.available_at for row in selected),
        lineage_ids=tuple(sorted({row.record_lineage_id for row in selected})),
        modalities=tuple(sorted({row.source_modality for row in selected})),
        quality_state=combine_quality(row.quality_state for row in selected),
    )


class ProvenanceIndex:
    def __init__(self, observations: Iterable[CanonicalObservation]) -> None:
        grouped: dict[tuple[str, str], list[CanonicalObservation]] = {}
        for row in observations:
            if not is_usable(row):
                continue
            grouped.setdefault((row.entity_id, row.variable_id), []).append(row)
        self._rows = {
            key: tuple(sorted(values, key=lambda row: row.decision_time))
            for key, values in grouped.items()
        }
        self._times = {
            key: tuple(row.decision_time for row in values)
            for key, values in self._rows.items()
        }

    def collect(
        self,
        *,
        entity_id: str,
        decision_time: datetime,
        requirements: Mapping[str, int],
    ) -> Provenance | None:
        rows: list[CanonicalObservation] = []
        for variable_id, count in requirements.items():
            if count < 1:
                continue
            key = (entity_id, variable_id)
            values = self._rows.get(key, ())
            times = self._times.get(key, ())
            end = bisect_right(times, decision_time)
            rows.extend(values[max(0, end - count):end])
        return from_observations(rows)

    def collect_many(
        self,
        *,
        decision_time: datetime,
        requirements: Iterable[tuple[str, str, int]],
    ) -> Provenance | None:
        rows: list[CanonicalObservation] = []
        for entity_id, variable_id, count in requirements:
            if count < 1:
                continue
            key = (entity_id, variable_id)
            values = self._rows.get(key, ())
            times = self._times.get(key, ())
            end = bisect_right(times, decision_time)
            rows.extend(values[max(0, end - count):end])
        return from_observations(rows)
