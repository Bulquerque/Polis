from __future__ import annotations

from datetime import datetime

from .contracts.canonicalization import canonical_sha256
from .models.artifacts import S5ResultBundle
from .models.inputs import ArtifactEnvelope, DecisionReadyRiskBundle
from .orchestration import execute_s5
from .version import __version__


def run_s5(bundle: DecisionReadyRiskBundle, *, processing_time: datetime) -> S5ResultBundle:
    if processing_time.tzinfo is None:
        raise ValueError("processing_time must be timezone-aware")
    if processing_time < bundle.envelope.decision_time:
        raise ValueError("processing_time cannot precede decision_time")
    payload = execute_s5(bundle)
    now = processing_time
    envelope = ArtifactEnvelope(
        artifact_id=f"{bundle.envelope.run_id}:P8.S5:RESULT",
        artifact_type="P8_TARGET_AND_CONTROL_PLAN_V1",
        schema_version="1.0.0",
        contract_version="1.0.0",
        producer_phase="P8",
        producer_module="P8.S5",
        producer_release=__version__,
        pipeline_version=bundle.envelope.pipeline_version,
        run_id=bundle.envelope.run_id,
        cycle_id=bundle.envelope.cycle_id,
        decision_time=bundle.envelope.decision_time,
        market_cutoff_at=bundle.envelope.market_cutoff_at,
        computed_at=now,
        recorded_at=now,
        available_at=now,
        content_sha256=canonical_sha256(payload),
        lineage_id=bundle.envelope.lineage_id,
    )
    return S5ResultBundle(envelope=envelope, payload=payload)
