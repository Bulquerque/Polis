from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import (
    canonical_sha256,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import (
    ArtifactEnvelope,
    DecisionReadyRiskBundle,
)

from .models.artifacts import ExecutionAuthorizationBundle
from .models.inputs import RiskLifecycleContextBundle
from .orchestration import execute_s6
from .version import __version__


def _validate_processing_time(
    risk_bundle: DecisionReadyRiskBundle,
    processing_time: datetime,
) -> None:
    if processing_time.tzinfo is None:
        raise ValueError("processing_time must be timezone-aware")
    if processing_time < risk_bundle.envelope.decision_time:
        raise ValueError("processing_time cannot precede decision time")


def _build_envelope(
    risk_bundle: DecisionReadyRiskBundle,
    payload_hash: str,
    processing_time: datetime,
) -> ArtifactEnvelope:
    source = risk_bundle.envelope
    return ArtifactEnvelope(
        artifact_id=f"{source.run_id}:P8.S6:AUTHORIZATION",
        artifact_type="P8_EXECUTION_AUTHORIZATION_BUNDLE_V1",
        schema_version="1.0.0",
        contract_version="1.0.0",
        producer_phase="P8",
        producer_module="P8.S6",
        producer_release=__version__,
        pipeline_version=source.pipeline_version,
        run_id=source.run_id,
        cycle_id=source.cycle_id,
        decision_time=source.decision_time,
        market_cutoff_at=source.market_cutoff_at,
        computed_at=processing_time,
        recorded_at=processing_time,
        available_at=processing_time,
        content_sha256=payload_hash,
        lineage_id=source.lineage_id,
    )


def run_s6(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    context: RiskLifecycleContextBundle,
    *,
    processing_time: datetime,
) -> ExecutionAuthorizationBundle:
    _validate_processing_time(risk_bundle, processing_time)
    payload = execute_s6(
        risk_bundle,
        s5_bundle,
        context,
        processing_time=processing_time,
    )
    envelope = _build_envelope(
        risk_bundle,
        canonical_sha256(payload),
        processing_time,
    )
    return ExecutionAuthorizationBundle(envelope=envelope, payload=payload)
