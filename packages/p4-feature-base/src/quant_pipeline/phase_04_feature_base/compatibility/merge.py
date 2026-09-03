from __future__ import annotations

from ..artifact_protocol import lineage_hash, stable_hash
from ..economic_models import CanonicalObservationPanel, ExecutionContext


def merge_canonical_panels(panels: list[CanonicalObservationPanel], context: ExecutionContext) -> CanonicalObservationPanel:
    records = tuple(row for panel in panels for row in panel.records)
    return CanonicalObservationPanel(
        artifact_id=f"canonical-merged:{stable_hash([row.model_dump(mode='json') for row in records])[:16]}",
        schema_version="p4.canonical.v1",
        pipeline_version=context.pipeline_version,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        created_at=context.created_at,
        lineage_id=lineage_hash(panel.lineage_id for panel in panels),
        records=records,
    )
