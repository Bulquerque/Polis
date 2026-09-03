from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re

import pandas as pd

from ..economic_errors import ContractError
from ..feature_records import one_record
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec
from ..provenance import combine_quality, from_observations, is_usable

MODULE_ID = "P4.S4.M06"
SUPPORTED_OBSERVERS = {
    "macro.level",
    "macro.change_1",
    "macro.acceleration",
    "macro.surprise",
    "event.time_distance",
    "calendar.day_of_week",
    "calendar.month",
    "calendar.is_month_end",
    "calendar.is_quarter_end",
}


def _suffix(variable_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", variable_id).strip("_")


def _macro_series(observations: tuple[CanonicalObservation, ...]) -> dict[tuple[str, str], list[CanonicalObservation]]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for row in observations:
        if (
            row.source_modality == "macro"
            and is_usable(row)
            and isinstance(row.value, (int, float))
            and not isinstance(row.value, bool)
        ):
            grouped[(row.entity_id, row.variable_id)].append(row)
    return grouped


def _dynamic_spec(spec: ObserverSpec, feature_id: str) -> ObserverSpec:
    return spec.model_copy(update={"feature_id": feature_id})


def _macro_records(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    output: list[AtomicFeatureRecord] = []
    for (entity_id, variable_id), rows in sorted(_macro_series(observations).items()):
        ordered = sorted(rows, key=lambda row: row.decision_time)
        values = pd.Series([float(row.value) for row in ordered], index=[row.decision_time for row in ordered])
        if spec.observer_id == "macro.level":
            computed, dependency_count = values, 1
        elif spec.observer_id == "macro.change_1":
            computed, dependency_count = values.diff(), 2
        elif spec.observer_id == "macro.acceleration":
            computed, dependency_count = values.diff().diff(), 3
        else:
            continue
        dynamic = _dynamic_spec(spec, f"{spec.feature_id}.{_suffix(variable_id)}")
        for index, (row, value) in enumerate(zip(ordered, computed, strict=True)):
            provenance = from_observations(ordered[max(0, index - dependency_count + 1):index + 1])
            if provenance is None:
                continue
            output.append(
                one_record(
                    decision_time=row.decision_time,
                    entity_id=entity_id,
                    spec=dynamic,
                    value=None if pd.isna(value) else float(value),
                    unit=row.unit or "native_unit",
                    available_at=provenance.available_at,
                    lineage_ids=provenance.lineage_ids,
                    modalities=provenance.modalities,
                    quality_state=provenance.quality_state,
                    attributes={"source_variable_id": variable_id, "reference_time": row.reference_time},
                )
            )
    return output


def _surprise_records(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    events: dict[tuple[str, str], dict[str, list[CanonicalObservation]]] = defaultdict(lambda: defaultdict(list))
    for row in observations:
        if (
            row.source_modality != "macro"
            or not is_usable(row)
            or not isinstance(row.value, (int, float))
            or isinstance(row.value, bool)
        ):
            continue
        event_id = row.attributes.get("event_id")
        role = str(row.attributes.get("value_role", ""))
        if event_id and role in {"ACTUAL", "EXPECTATION"}:
            events[(row.entity_id, str(event_id))][role].append(row)
    output: list[AtomicFeatureRecord] = []
    for (entity_id, event_id), roles in sorted(events.items()):
        for actual in sorted(roles.get("ACTUAL", ()), key=lambda row: row.decision_time):
            eligible = [
                row
                for row in roles.get("EXPECTATION", ())
                if row.available_at <= actual.decision_time
            ]
            if not eligible:
                continue
            expectation = max(eligible, key=lambda row: (row.available_at, row.record_lineage_id))
            if actual.unit and expectation.unit and actual.unit != expectation.unit:
                raise ContractError(
                    "P4_S4_M06_SURPRISE_UNIT_MISMATCH",
                    "macro actual and expectation units differ",
                    details={"event_id": event_id, "actual_unit": actual.unit, "expectation_unit": expectation.unit},
                )
            provenance = from_observations((actual, expectation))
            if provenance is None:
                continue
            output.append(
                one_record(
                    decision_time=actual.decision_time,
                    entity_id=entity_id,
                    spec=spec,
                    value=float(actual.value) - float(expectation.value),
                    unit=actual.unit or expectation.unit or "native_unit",
                    available_at=provenance.available_at,
                    lineage_ids=provenance.lineage_ids,
                    modalities=provenance.modalities,
                    quality_state=provenance.quality_state,
                    attributes={"event_id": event_id, "expectation_available_at": expectation.available_at},
                )
            )
    return output


def _event_records(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    grouped: dict[tuple[datetime, str, str], list[CanonicalObservation]] = defaultdict(list)
    for row in observations:
        if row.source_modality != "event" or row.event_time is None or not is_usable(row):
            continue
        event_id = str(row.attributes.get("event_id") or row.source_id or row.record_lineage_id)
        grouped[(row.decision_time, row.entity_id, event_id)].append(row)

    output: list[AtomicFeatureRecord] = []
    for (decision_time, entity_id, event_id), rows in sorted(grouped.items()):
        event_times = {row.event_time for row in rows}
        if len(event_times) != 1:
            raise ContractError(
                "P4_S4_M06_EVENT_TIME_CONFLICT",
                "event fields disagree on event_time",
                details={"event_id": event_id, "event_times": sorted(map(str, event_times))},
            )
        event_time = next(iter(event_times))
        days = (event_time - decision_time).total_seconds() / 86_400.0
        output.append(
            one_record(
                decision_time=decision_time,
                entity_id=entity_id,
                spec=spec,
                value=float(days),
                unit="days",
                available_at=max(row.available_at for row in rows),
                lineage_ids=[row.record_lineage_id for row in rows],
                modalities=[row.source_modality for row in rows],
                quality_state=combine_quality(row.quality_state for row in rows),
                attributes={
                    "event_id": event_id,
                    "event_type": next(
                        (row.attributes.get("event_type") for row in rows if row.attributes.get("event_type")),
                        None,
                    ),
                    "deduplicated_field_count": len(rows),
                },
            )
        )
    return output


def _calendar_records(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    grouped: dict[tuple[datetime, str], list[CanonicalObservation]] = defaultdict(list)
    for row in observations:
        if is_usable(row):
            grouped[(row.decision_time, row.entity_id)].append(row)
    output: list[AtomicFeatureRecord] = []
    for (decision_time, entity_id), rows in sorted(grouped.items()):
        stamp = pd.Timestamp(decision_time)
        if spec.observer_id == "calendar.day_of_week":
            value, unit = float(stamp.dayofweek), "category_index"
        elif spec.observer_id == "calendar.month":
            value, unit = float(stamp.month), "category_index"
        elif spec.observer_id == "calendar.is_month_end":
            value, unit = float(stamp.is_month_end), "boolean"
        elif spec.observer_id == "calendar.is_quarter_end":
            value, unit = float(stamp.is_quarter_end), "boolean"
        else:
            continue
        output.append(
            one_record(
                decision_time=decision_time,
                entity_id=entity_id,
                spec=spec,
                value=value,
                unit=unit,
                available_at=max(row.available_at for row in rows),
                lineage_ids=[row.record_lineage_id for row in rows],
                modalities=["calendar"],
                quality_state=combine_quality(row.quality_state for row in rows),
            )
        )
    return output


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    output: list[AtomicFeatureRecord] = []
    for spec in specs:
        if spec.observer_id.startswith("macro.") and spec.observer_id != "macro.surprise":
            output.extend(_macro_records(observations, spec))
        elif spec.observer_id == "macro.surprise":
            output.extend(_surprise_records(observations, spec))
        elif spec.observer_id == "event.time_distance":
            output.extend(_event_records(observations, spec))
        elif spec.observer_id.startswith("calendar."):
            output.extend(_calendar_records(observations, spec))
    return output
