from __future__ import annotations

import math

from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord, PerspectiveSpec
from ..perspective_records import one_perspective

SUPPORTED_OBSERVERS = {"event.surprise_state", "event.proximity_state"}


def compute(
    records: tuple,
    specs: tuple[PerspectiveSpec, ...],
) -> list[PerspectiveFeatureRecord]:
    index = AtomicRecordIndex(records)
    output: list[PerspectiveFeatureRecord] = []
    for spec in specs:
        feature_id = spec.source_feature_ids[0]
        half_life = float(spec.parameters.get("half_life_days", 10.0))
        for entity_id in index.entities(feature_id):
            for decision_time, raw_value in index.series(entity_id, feature_id).items():
                value = float(raw_value)
                is_proximity = spec.observer_id == "event.proximity_state"
                if is_proximity:
                    direction = 1 if value >= 0 else -1
                    value = direction * math.exp(-abs(value) / half_life)
                provenance = index.collect(
                    entity_id=entity_id,
                    decision_time=decision_time,
                    requirements={feature_id: 1},
                )
                if provenance is None:
                    continue
                sign_convention = (
                    "POSITIVE_PROXIMITY_MEANS_UPCOMING_NEGATIVE_MEANS_ELAPSED"
                    if is_proximity
                    else "SIGNED_EVENT_SURPRISE"
                )
                output.append(
                    one_perspective(
                        decision_time=decision_time,
                        entity_id=entity_id,
                        spec=spec,
                        value=value,
                        unit="event_state",
                        sign_convention=sign_convention,
                        provenance=provenance,
                        attributes={
                            "half_life_days": half_life if is_proximity else None
                        },
                    )
                )
    return output
