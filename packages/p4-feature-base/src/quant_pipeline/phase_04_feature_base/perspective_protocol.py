from __future__ import annotations

from typing import Iterable

from .artifact_protocol import stable_hash
from .economic_models import ExecutionContext, ExecutionStatus, QualityState
from .perspective_models import PerspectiveFeaturePanel, PerspectiveFeatureRecord

SCHEMA_VERSION="p4.s5.perspective.v1"


def perspective_lineage_hash(lineage_ids):
    values=sorted({value for value in lineage_ids if value})
    return f"lineage-p4-s5-{stable_hash(values)[:24]}"


def build_perspective_panel(*,artifact_name:str,module_id:str,context:ExecutionContext,records:list[PerspectiveFeatureRecord],execution_status:ExecutionStatus,quality_status:QualityState,quality_reasons:tuple[str,...]=(),upstream_lineage_ids:Iterable[str]=()) -> PerspectiveFeaturePanel:
    ordered=sorted(records,key=lambda r:(r.decision_time,r.entity_id,r.feature_id,r.observer_id))
    payload=[r.model_dump(mode="json") for r in ordered]
    content_hash=stable_hash({"artifact_name":artifact_name,"records":payload})
    return PerspectiveFeaturePanel(
        artifact_id=f"{artifact_name}:{content_hash[:16]}",artifact_name=artifact_name,schema_version=SCHEMA_VERSION,
        pipeline_version=context.pipeline_version,producer_module_id=module_id,run_id=context.run_id,cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,created_at=context.created_at,content_hash=content_hash,
        lineage_id=perspective_lineage_hash([*upstream_lineage_ids,*(r.record_lineage_id for r in ordered)]),
        execution_status=execution_status,quality_status=quality_status,quality_reasons=quality_reasons,records=tuple(ordered),
    )
