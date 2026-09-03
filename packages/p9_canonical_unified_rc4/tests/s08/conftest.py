from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation import (
    ArtifactReference,
    ProspectiveMonitoringBundle,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    Availability,
    EvidenceClass,
)
from quant_pipeline.phase_09.subphases.s08_attribution.bundle import (
    S8ExecutionRequest,
)
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import (
    S8BundleHeader,
    S8ConsumerReceipt,
    S8UpstreamReferences,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m01_forecast_attribution import (
    ForecastAttributionPolicy,
    ForecastComponentObservation,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m02_payoff_attribution import (
    CandidateOutcome,
    PayoffAttributionPolicy,
    PayoffScenarioPoint,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m03_ranking_attribution import (
    RankedCandidate,
    RankingAttributionPolicy,
    RankingGroup,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m04_portfolio_attribution import (
    CandidateAllocationRecord,
    PhysicalPositionLedgerItem,
    PortfolioAttributionPolicy,
    VirtualCandidateLedgerItem,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m05_execution_attribution import (
    ExecutionAttributionPolicy,
    ExecutionRecord,
    LifecycleEvent,
    OrderSide,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m06_option_attribution import (
    OptionAttributionInterval,
    OptionAttributionPolicy,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m07_counterfactual import (
    CounterfactualPolicy,
    LoggedPolicyObservation,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m08_reconciliation import (
    ReconciliationPolicy,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
SCHEMA_HASH = "d" * 64
NOW = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)


def _s7_bundle() -> ProspectiveMonitoringBundle:
    path = Path(__file__).parents[2] / "fixtures/s08/upstream/s7_prospective_monitoring_bundle.json"
    return ProspectiveMonitoringBundle.model_validate_json(path.read_text())


def _artifact(artifact_id: str, digest: str, producer: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        artifact_type="subphase_bundle",
        artifact_schema_name=f"{artifact_id}.schema.json",
        artifact_schema_version="1.0.0",
        artifact_schema_sha256=SCHEMA_HASH,
        content_sha256=digest,
        producer_module_id=producer,
        run_id="run-1",
        cycle_id="cycle-1",
        decision_time=NOW,
        available_at=NOW,
        computed_at=NOW,
        uri=f"artifact://{artifact_id}",
        availability=Availability.AVAILABLE,
    )


def _receipt(module_id: str, name: str, digest: str, artifact_id: str) -> S8ConsumerReceipt:
    return S8ConsumerReceipt(
        consumer_module_id=module_id,
        source_contract_name=name,
        source_contract_version="1.0.0",
        source_bundle_sha256=digest,
        input_ref_ids=(artifact_id,),
        accepted_ref_ids=(artifact_id,),
    )


def build_valid_request() -> S8ExecutionRequest:
    foundation_ref = _artifact("foundation-bundle", HASH_A, "P9.S2.M06")
    backtest_ref = _artifact("backtest-metrics-bundle", HASH_B, "P9.S4.M08")
    robustness_ref = _artifact("robustness-stress-bundle", HASH_C, "P9.S6.M08")
    upstream = S8UpstreamReferences(
        foundation_bundle=foundation_ref,
        backtest_metrics_bundle=backtest_ref,
        robustness_stress_bundle=robustness_ref,
        consumer_receipts=(
            _receipt("P9.S8.M01", "P9_FOUNDATION_EXPERIMENT_BUNDLE_V1", HASH_A, "foundation-bundle"),
            _receipt("P9.S8.M01", "P9_BACKTEST_METRICS_BUNDLE_V1", HASH_B, "backtest-metrics-bundle"),
            _receipt("P9.S8.M02", "P9_ROBUSTNESS_STRESS_BUNDLE_V1", HASH_C, "robustness-stress-bundle"),
        ),
    )
    forecast_rows = tuple(
        ForecastComponentObservation(
            observation_id=f"obs-{index}",
            target_id="target",
            horizon_id="h1",
            regime_id="normal",
            component_id="model-a",
            component_kind="MODEL",
            consumed=True,
            historical_weight=1.0,
            ensemble_loss=0.1,
            ablated_loss=0.2,
            component_prediction=float(index),
            oof_qualified=True,
            observable_pnl_with_component=1.0 / 3.0,
            observable_pnl_without_component=0.0,
            evidence_class=EvidenceClass.OBSERVABLE_COUNTERFACTUAL,
        )
        for index in range(3)
    )
    scenarios = tuple(
        PayoffScenarioPoint(
            candidate_id=candidate_id,
            scenario_id=f"{candidate_id}-s{index}",
            target_payoff_per_unit=value,
            candidate_payoff_per_unit=value,
            probability_weight=1.0,
        )
        for candidate_id in ("c1", "c2")
        for index, value in enumerate((-1.0, 0.0, 2.0), start=1)
    )
    outcomes = (
        CandidateOutcome(
            candidate_id="c1",
            selected_by_p6=True,
            observable=True,
            realized_unit_pnl=4.0,
            estimated_price=10.0,
            actual_price=10.0,
            estimated_cost=0.1,
            actual_cost=0.1,
            maximum_loss_bound=2.0,
            observed_loss=1.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
        CandidateOutcome(
            candidate_id="c2",
            selected_by_p6=False,
            observable=True,
            realized_unit_pnl=2.0,
            evidence_class=EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
        ),
    )
    ranking = (
        RankingGroup(
            group_id="g1",
            candidates=(
                RankedCandidate(
                    group_id="g1",
                    candidate_id="c1",
                    predicted_rank=1,
                    predicted_score=2.0,
                    realized_utility=4.0,
                    evidence_class=EvidenceClass.FACTUAL_EXECUTED,
                    confidence=0.9,
                    dominates_candidate_ids=("c2",),
                ),
                RankedCandidate(
                    group_id="g1",
                    candidate_id="c2",
                    predicted_rank=2,
                    predicted_score=1.0,
                    realized_utility=2.0,
                    evidence_class=EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
                    confidence=0.8,
                ),
            ),
        ),
    )
    allocations = (
        CandidateAllocationRecord(
            candidate_id="c1",
            selected=True,
            ranking_position=1,
            realized_unit_pnl=5.0,
            reference_quantity=1.0,
            unconstrained_quantity=1.0,
            constrained_quantity=1.0,
            discrete_quantity=1.0,
        ),
        CandidateAllocationRecord(
            candidate_id="c2",
            selected=False,
            ranking_position=2,
            realized_unit_pnl=2.0,
            reference_quantity=1.0,
            unconstrained_quantity=0.0,
            constrained_quantity=0.0,
            discrete_quantity=0.0,
        ),
    )
    virtual = (
        VirtualCandidateLedgerItem(
            candidate_id="c1",
            discrete_quantity=1.0,
            realized_virtual_pnl=5.0,
            instrument_quantities=(("asset", 1.0),),
        ),
    )
    physical = (
        PhysicalPositionLedgerItem(
            instrument_id="asset",
            net_quantity=1.0,
            realized_physical_pnl=5.0,
        ),
    )
    execution = (
        ExecutionRecord(
            order_id="o1",
            side=OrderSide.BUY,
            target_quantity=1.0,
            ordered_quantity=1.0,
            filled_quantity=1.0,
            decision_price=10.0,
            arrival_price=10.0,
            average_fill_price=10.0,
            evaluation_price=10.0,
            estimated_slippage_cost=0.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
    )
    lifecycle = (
        LifecycleEvent(
            position_id="p1",
            planned_event="HOLD",
            actual_event="HOLD",
            planned_pnl=0.0,
            actual_pnl=0.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
    )
    options = (
        OptionAttributionInterval(
            position_id="opt1",
            interval_start=NOW,
            interval_end=NOW,
            greek_snapshot_time=NOW,
            quantity=1.0,
            price_before=10.0,
            price_after=11.0,
            delta=1.0,
            gamma=0.0,
            vega=0.0,
            theta_per_year=0.0,
            rho=0.0,
            spot_change=1.0,
            volatility_change=0.0,
            year_fraction=0.0,
            rate_change=0.0,
        ),
    )
    logged = tuple(
        LoggedPolicyObservation(
            observation_id=f"ope-{index}",
            action_id="c1",
            reward=1.0,
            logging_propensity=1.0,
            target_action_probability=1.0,
            direct_model_chosen_reward=1.0,
            direct_model_target_value=1.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        )
        for index in range(10)
    )
    return S8ExecutionRequest(
        header=S8BundleHeader(run_id="run-1", cycle_id="cycle-1", created_at=NOW),
        upstream=upstream,
        s7_bundle=_s7_bundle(),
        forecast_observations=forecast_rows,
        forecast_policy=ForecastAttributionPolicy(),
        payoff_scenario_points=scenarios,
        candidate_outcomes=outcomes,
        payoff_policy=PayoffAttributionPolicy(),
        ranking_groups=ranking,
        ranking_policy=RankingAttributionPolicy(),
        allocation_records=allocations,
        virtual_candidate_ledger=virtual,
        physical_position_ledger=physical,
        portfolio_policy=PortfolioAttributionPolicy(),
        execution_records=execution,
        lifecycle_events=lifecycle,
        execution_policy=ExecutionAttributionPolicy(),
        option_intervals=options,
        option_policy=OptionAttributionPolicy(),
        logged_policy_observations=logged,
        counterfactual_policy=CounterfactualPolicy(),
        factual_pnl=6.0,
        reconciliation_policy=ReconciliationPolicy(),
    )


@pytest.fixture
def valid_request() -> S8ExecutionRequest:
    return build_valid_request()
