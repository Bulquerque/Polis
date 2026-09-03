from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_08_portfolio_control.s05_optimization import run_s5
from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import ArtifactEnvelope, DecisionReadyRiskBundle
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle import run_s6
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.inputs import RiskLifecycleContextBundle

from .models import Agent3IntegratedBundle, Agent3IntegratedPayload
from .version import __version__


def _validate_times(s5_processing_time: datetime, s6_processing_time: datetime) -> None:
    if s5_processing_time.tzinfo is None or s6_processing_time.tzinfo is None:
        raise ValueError("processing times must be timezone-aware")
    if s6_processing_time < s5_processing_time:
        raise ValueError("S6 processing time cannot precede S5 processing time")


def run_agent3(
    risk_bundle: DecisionReadyRiskBundle,
    lifecycle_context: RiskLifecycleContextBundle,
    *,
    s5_processing_time: datetime,
    s6_processing_time: datetime,
) -> Agent3IntegratedBundle:
    """Execute the canonical S5→S6 chain without bypassing either public API."""
    _validate_times(s5_processing_time, s6_processing_time)
    s5_result = run_s5(risk_bundle, processing_time=s5_processing_time)
    s6_result = run_s6(
        risk_bundle,
        s5_result,
        lifecycle_context,
        processing_time=s6_processing_time,
    )
    payload = Agent3IntegratedPayload(
        s5_result=s5_result,
        s6_authorization=s6_result,
        integration_receipts=(
            "P8.S5:PUBLIC_API_EXECUTED",
            "P8.S5_TO_S6:CONSUMER_CONTRACT_PASS",
            "P8.S6:PUBLIC_API_EXECUTED",
        ),
    )
    source = risk_bundle.envelope
    envelope = ArtifactEnvelope(
        artifact_id=f"{source.run_id}:P8.AGENT3:RESULT",
        artifact_type="P8_AGENT_3_S5_S6_RESULT_V1",
        schema_version="1.0.0",
        contract_version="1.0.0",
        producer_phase="P8",
        producer_module="P8.AGENT3.S5_S6",
        producer_release=__version__,
        pipeline_version=source.pipeline_version,
        run_id=source.run_id,
        cycle_id=source.cycle_id,
        decision_time=source.decision_time,
        market_cutoff_at=source.market_cutoff_at,
        computed_at=s6_processing_time,
        recorded_at=s6_processing_time,
        available_at=s6_processing_time,
        content_sha256=canonical_sha256(payload),
        lineage_id=source.lineage_id,
    )
    return Agent3IntegratedBundle(envelope=envelope, payload=payload)
