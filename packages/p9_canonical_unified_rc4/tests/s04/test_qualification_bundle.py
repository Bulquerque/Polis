from __future__ import annotations

from datetime import UTC, datetime, timedelta

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import TerminalStatus
from quant_pipeline.phase_09.subphases.s04_performance_risk.qualification import (
    artifact_reference,
    build_backtest_metrics_bundle,
    build_module_receipt,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.service import (
    S4AnalyticsRequest,
    S4AnalyticsService,
)


def _run(
    qualified,
    policies,
    benchmark,
    risk_free,
    factor_panel,
    registries,
    execution_inputs,
):
    targets, liquidity, exposures = execution_inputs
    return S4AnalyticsService().run(
        S4AnalyticsRequest(
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
    )


def test_build_backtest_metrics_bundle_with_exact_module_conservation(
    qualified,
    policies,
    benchmark,
    risk_free,
    factor_panel,
    registries,
    execution_inputs,
):
    result = _run(
        qualified,
        policies,
        benchmark,
        risk_free,
        factor_panel,
        registries,
        execution_inputs,
    )
    now = datetime(2026, 8, 3, 20, 0, tzinfo=UTC)
    s4_ref = artifact_reference(
        artifact_id=result.quality.panel.panel_id,
        artifact_type="INSTITUTIONAL_METRIC_PANEL",
        schema_name="InstitutionalMetricPanel",
        content_sha256=result.quality.panel.content_sha256,
        producer_module_id="P9.S4.M08",
        run_id=result.quality.panel.identity.run_id,
        cycle_id=result.quality.panel.identity.cycle_id,
        available_at=now,
        location="memory://metric-panel",
        record_count=result.quality.panel.metric_count,
    )
    module_refs = tuple(
        artifact_reference(
            artifact_id=f"s4-m{index:02d}-output",
            artifact_type="S4_MODULE_OUTPUT",
            schema_name="ModuleOutputReference",
            content_sha256=result.quality.panel.content_sha256,
            producer_module_id=f"P9.S4.M{index:02d}",
            run_id=result.quality.panel.identity.run_id,
            cycle_id=result.quality.panel.identity.cycle_id,
            available_at=now,
            location=f"memory://s4-m{index:02d}",
        )
        for index in range(1, 9)
    )
    receipts = tuple(
        build_module_receipt(
            module_id=f"P9.S4.M{index:02d}",
            started_at=now,
            completed_at=now + timedelta(seconds=index),
            input_refs=(),
            output_refs=(module_refs[index - 1],),
            status=TerminalStatus.SUCCESS,
        )
        for index in range(1, 9)
    )
    bundle = build_backtest_metrics_bundle(
        quality=result.quality,
        s3_artifact_refs=(),
        s4_artifact_refs=(s4_ref,),
        module_receipts=receipts,
        upstream_bundle_sha256=qualified.handoff.replay_sha256,
    )
    assert len(bundle.module_receipts) == 8
    assert bundle.metric_panel.metric_count == result.quality.panel.metric_count
