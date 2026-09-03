from __future__ import annotations

from quant_pipeline.phase_09.subphases.s04_performance_risk.execution_models import ExecutionCapacityRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.m07_execution_capacity import compute_execution_capacity


def test_execution_metrics_and_capacity(qualified, policies, execution_inputs):
    targets, liquidity, exposures = execution_inputs
    result = compute_execution_capacity(
        ExecutionCapacityRequest(
            identity=qualified.identity(),
            handoff=qualified.handoff,
            target_contexts=targets,
            liquidity=liquidity,
            exposures=exposures,
            policy=policies["capacity"],
            baseline_net_return=0.10,
        )
    )
    fill_rate = next(record for record in result.execution.execution_metrics if record.metric_id == "execution.fill_rate")
    assert fill_rate.value == 1.0
    assert result.costs.total_fees > 0
    assert result.costs.observed_slippage is not None
    assert len(result.capacity.points) == len(policies["capacity"].aum_multipliers)
    impacts = [point.estimated_impact_fraction for point in result.capacity.points]
    assert impacts == sorted(impacts)


def test_missing_execution_context_is_limited(qualified, policies):
    result = compute_execution_capacity(
        ExecutionCapacityRequest(
            identity=qualified.identity(),
            handoff=qualified.handoff,
            policy=policies["capacity"],
        )
    )
    fill_rate = next(record for record in result.execution.execution_metrics if record.metric_id == "execution.fill_rate")
    assert fill_rate.value is None
    assert fill_rate.status == "UNAVAILABLE"
    assert result.capacity.evidence_class.value == "PARAMETRIC_IMPACT"
