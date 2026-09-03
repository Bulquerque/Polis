from __future__ import annotations

from quant_pipeline.phase_09.subphases.s04_performance_risk.bundle_models import MetricQualityRequest, QualityState
from quant_pipeline.phase_09.subphases.s04_performance_risk.service import S4AnalyticsRequest, S4AnalyticsService


def build_request(qualified, policies, benchmark, risk_free, factor_panel, registries, execution_inputs):
    targets, liquidity, exposures = execution_inputs
    return S4AnalyticsRequest(
        qualified_backtest=qualified,
        return_policy=policies["return"],
        distribution_policy=policies["distribution"],
        tail_policy=policies["tail"],
        drawdown_policy=policies["drawdown"],
        risk_adjusted_policy=policies["risk_adjusted"],
        capacity_policy=policies["capacity"],
        metric_registry=registries[0],
        metric_quality_policy=policies["quality"],
        benchmark=benchmark,
        risk_free=risk_free,
        factor_panel=factor_panel,
        factor_registry=registries[1],
        regression_policy=policies["regression"],
        target_contexts=targets,
        liquidity=liquidity,
        exposures=exposures,
    )


def test_quality_gate_accepts_registered_metrics(qualified, policies, benchmark, risk_free, factor_panel, registries, execution_inputs):
    result = S4AnalyticsService().run(
        build_request(qualified, policies, benchmark, risk_free, factor_panel, registries, execution_inputs)
    )
    assert result.quality.receipt.state in {QualityState.QUALIFIED, QualityState.QUALIFIED_WITH_LIMITATIONS}
    assert result.quality.panel.metric_count == len(result.quality.panel.metrics)
    assert result.quality.panel.metric_count > 20


def test_registry_drift_invalidates_panel(qualified, policies, benchmark, risk_free, factor_panel, registries, execution_inputs):
    result = S4AnalyticsService().run(
        build_request(qualified, policies, benchmark, risk_free, factor_panel, registries, execution_inputs)
    )
    reduced = registries[0].model_copy(
        update={
            "entries": tuple(entry for entry in registries[0].entries if entry.metric_pattern != "return.cumulative"),
            "content_sha256": "0" * 64,
        }
    )
    from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
    body = reduced.model_dump(mode="python", exclude={"content_sha256"})
    reduced = reduced.model_copy(update={"content_sha256": content_sha256(body)})
    from quant_pipeline.phase_09.subphases.s04_performance_risk.m08_quality_gate import reconcile_metrics
    request = MetricQualityRequest(
        returns=result.returns,
        distribution=result.distribution,
        tails=result.tails,
        drawdowns=result.drawdowns,
        risk_adjusted=result.risk_adjusted,
        factors=result.factors,
        execution=result.execution,
        registry=reduced,
        policy=policies["quality"],
    )
    quality = reconcile_metrics(request)
    assert quality.receipt.state is QualityState.INVALID
    assert "P9_S4_METRIC_REGISTRY_DRIFT" in quality.receipt.reason_codes
