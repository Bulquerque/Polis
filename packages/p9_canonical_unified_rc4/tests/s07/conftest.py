from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    ArtifactReference,
    Availability,
    BundleHeader,
    ConsumerReceipt,
    EvidenceClass,
    MaturityState,
    S7MaterializationReceipt,
    S7UpstreamReferences,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import (
    BinaryProbabilityForecast,
    DecisionKind,
    IntervalForecast,
    NormalForecast,
    OutcomeEvent,
    PredictionEvent,
)


def h(text: str) -> str:
    return sha256(text.encode()).hexdigest()


@pytest.fixture()
def base_time() -> datetime:
    return datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture()
def upstream(base_time: datetime) -> S7UpstreamReferences:
    refs = []
    for idx, (artifact_type, producer) in enumerate(
        (
            ("P9_FOUNDATION_EXPERIMENT_BUNDLE_V1", "P9.S1.M06"),
            ("P9_BACKTEST_METRICS_BUNDLE_V1", "P9.S4.M08"),
            ("P9_ROBUSTNESS_STRESS_BUNDLE_V1", "P9.S6.M08"),
        ),
        start=1,
    ):
        refs.append(
            ArtifactReference(
                artifact_id=f"upstream-{idx}",
                artifact_type=artifact_type,
                artifact_schema_name=artifact_type,
                artifact_schema_version="1.0.0",
                artifact_schema_sha256=h(f"schema-{idx}"),
                content_sha256=h(f"content-{idx}"),
                producer_module_id=producer,
                run_id="run-1",
                cycle_id="cycle-1",
                decision_time=base_time,
                available_at=base_time - timedelta(hours=1),
                computed_at=base_time - timedelta(minutes=30),
                uri=f"artifact://upstream/{idx}",
                availability=Availability.AVAILABLE,
            )
        )
    receipts = tuple(
        ConsumerReceipt(
            consumer_module_id="P9.S7.M01",
            source_contract_name=ref.artifact_type,
            source_contract_version="1.0.0",
            source_bundle_sha256=ref.content_sha256,
            input_ref_ids=(ref.artifact_id,),
            accepted_ref_ids=(ref.artifact_id,),
        )
        for ref in refs
    )
    return S7UpstreamReferences(
        foundation_bundle=refs[0],
        backtest_metrics_bundle=refs[1],
        robustness_stress_bundle=refs[2],
        consumer_receipts=receipts,
    )


@pytest.fixture()
def header(base_time: datetime) -> BundleHeader:
    return BundleHeader(run_id="run-1", cycle_id="cycle-1", created_at=base_time)


def prediction(
    event_id: str,
    issued_at: datetime,
    policy_id: str = "champion",
    forecast=None,
    decision_kind: DecisionKind = DecisionKind.ACTION,
) -> PredictionEvent:
    return PredictionEvent(
        event_id=event_id,
        cohort_id=f"cohort-{event_id}",
        policy_id=policy_id,
        policy_version="1.0.0",
        target_id="return-1d",
        horizon_id="1d",
        issued_at=issued_at,
        information_set_hash=h(f"info-{event_id}"),
        forecast=forecast or NormalForecast(mean=0.0, standard_deviation=1.0),
        decision_kind=decision_kind,
        action_id=f"action-{event_id}" if decision_kind is DecisionKind.ACTION else None,
        regime_id="normal",
        ood_bucket="in_distribution",
        confidence_bucket="high",
    )


def outcome(
    prediction_event_id: str,
    issued_at: datetime,
    value: float,
    maturity: MaturityState = MaturityState.MATURED,
    suffix: str = "v1",
) -> OutcomeEvent:
    return OutcomeEvent(
        outcome_id=f"outcome-{prediction_event_id}-{suffix}",
        prediction_event_id=prediction_event_id,
        observed_at=issued_at + timedelta(days=1),
        available_at=issued_at + timedelta(days=1, minutes=5),
        maturity_state=maturity,
        evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        value=value if maturity in {MaturityState.MATURED, MaturityState.SETTLED} else None,
        vintage_id=suffix,
    )


@pytest.fixture()
def normal_prediction(base_time: datetime) -> PredictionEvent:
    return prediction("p1", base_time - timedelta(days=2))


@pytest.fixture()
def binary_prediction(base_time: datetime) -> PredictionEvent:
    return prediction(
        "p-binary",
        base_time - timedelta(days=2),
        forecast=BinaryProbabilityForecast(probability=0.8),
    )


@pytest.fixture()
def interval_prediction(base_time: datetime) -> PredictionEvent:
    return prediction(
        "p-interval",
        base_time - timedelta(days=2),
        forecast=IntervalForecast(lower=-1.0, upper=1.0, nominal_coverage=0.9),
    )


def make_execution_request(base_time, header, upstream, count: int = 40):
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m02_shadow import (
        DeploymentStage,
        PolicyExecutionOutput,
        PolicyRole,
        PolicySpecification,
        build_shadow_execution_plan,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m03_scoring import ScoringPolicy
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m04_conformal import (
        ConformalObservation,
        ConformalPolicy,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m05_drift import (
        DriftChannelKind,
        DriftChannelPolicy,
        DriftObservation,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m06_sequential import (
        PairedLossObservation,
        SequentialComparisonPolicy,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m07_rollback import (
        LiveExecutionMetrics,
        RollbackPolicy,
        StressCapacityQualification,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m08_reality_gap import (
        ExecutionStage,
        RealityGapPolicy,
        StageExecutionRecord,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import (
        IntervalForecast,
        build_prequential_stream,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.runner import S7ExecutionRequest

    predictions = tuple(
        prediction(
            f"p{i}",
            base_time - timedelta(days=count - i + 2),
            forecast=IntervalForecast(lower=-1.0, upper=1.0, nominal_coverage=0.9),
        )
        for i in range(count)
    )
    outcomes = tuple(
        outcome(item.event_id, item.issued_at, 0.2 if i % 10 else 1.5)
        for i, item in enumerate(predictions)
    )
    stream = build_prequential_stream(predictions, outcomes)
    champion = PolicySpecification(
        policy_id="champion",
        policy_version="1.0.0",
        role=PolicyRole.CHAMPION,
        code_sha256=h("champion-code"),
        resource_budget_units=10,
        seed_entropy=1,
        authorized_stage=DeploymentStage.SHADOW_ONLY,
    )
    challenger = PolicySpecification(
        policy_id="challenger",
        policy_version="1.0.0",
        role=PolicyRole.CHALLENGER,
        code_sha256=h("challenger-code"),
        resource_budget_units=10,
        seed_entropy=2,
        authorized_stage=DeploymentStage.SHADOW_ONLY,
    )
    plan = build_shadow_execution_plan(stream.records, champion, (challenger,))
    execution_outputs = tuple(
        PolicyExecutionOutput(
            cohort_id=entry.cohort_id,
            prediction_event_id=entry.prediction_event_id,
            policy_id=entry.policy_id,
            policy_version=entry.policy_version,
            information_set_hash=entry.information_set_hash,
            stage=entry.stage,
            started_at=base_time,
            completed_at=base_time,
            output_artifact_id=f"output-{entry.prediction_event_id}-{entry.policy_id}",
            output_sha256=h(f"output-{entry.prediction_event_id}-{entry.policy_id}"),
            execution_status="SUCCESS",
            resource_units_used=5,
        )
        for entry in plan.entries
    )
    conformal = tuple(
        ConformalObservation(
            event_id=f"conf-{i}",
            group_id="1d",
            lower=-1.0,
            upper=1.0,
            outcome=0.2 if i % 10 else 1.5,
        )
        for i in range(count)
    )
    drift_observations = tuple(
        DriftObservation(
            channel_id="residual",
            channel_kind=DriftChannelKind.FORECAST_RESIDUAL,
            observed_at=base_time + timedelta(minutes=i),
            value=0.0 if i < 30 else 0.1,
        )
        for i in range(40)
    ) + tuple(
        DriftObservation(
            channel_id="cost",
            channel_kind=DriftChannelKind.COST,
            observed_at=base_time + timedelta(minutes=i),
            value=0.0,
        )
        for i in range(40)
    )
    drift_policies = (
        DriftChannelPolicy(
            channel_id="residual",
            channel_kind=DriftChannelKind.FORECAST_RESIDUAL,
            reference_window=30,
            test_window=10,
            mean_shift_z_threshold=4.0,
            cusum_threshold=10.0,
            bocpd_alert_probability=0.9,
        ),
        DriftChannelPolicy(
            channel_id="cost",
            channel_kind=DriftChannelKind.COST,
            reference_window=30,
            test_window=10,
            mean_shift_z_threshold=4.0,
            cusum_threshold=10.0,
            bocpd_alert_probability=0.9,
        ),
    )
    paired = tuple(
        PairedLossObservation(
            cohort_id=f"cohort-{i}",
            prediction_event_id=f"paired-{i}",
            champion_policy_id="champion",
            challenger_policy_id="challenger",
            champion_loss=0.4,
            challenger_loss=0.4,
        )
        for i in range(count)
    )
    stage_records = []
    for i in range(5):
        for stage in (ExecutionStage.BACKTEST, ExecutionStage.SHADOW, ExecutionStage.LIVE):
            stage_records.append(
                StageExecutionRecord(
                    decision_id=f"d{i}",
                    cohort_id=f"cohort-d{i}",
                    policy_id="champion",
                    instrument_id="ABC",
                    horizon_id="1d",
                    stage=stage,
                    decision_time=base_time - timedelta(days=2),
                    forecast_value=0.1,
                    signal_value=1.0,
                    target_quantity=10.0,
                    order_quantity=10.0,
                    fill_quantity=10.0,
                    benchmark_price=100.0,
                    average_fill_price=100.1,
                    fees=1.0,
                    margin_used=100.0,
                    pnl=5.0,
                    evidence_class=(
                        EvidenceClass.FACTUAL_EXECUTED
                        if stage is ExecutionStage.LIVE
                        else EvidenceClass.MODEL_BASED_COUNTERFACTUAL
                    ),
                )
            )
    request_values = dict(
        header=header,
        upstream=upstream,
        predictions=predictions,
        outcomes=outcomes,
        champion_policy=champion,
        challenger_policies=(challenger,),
        policy_execution_outputs=execution_outputs,
        scoring_policy=ScoringPolicy(minimum_calibration_count=10),
        conformal_policy=ConformalPolicy(
            target_coverage=0.9,
            learning_rate=0.02,
            minimum_group_count=20,
            maximum_qualified_width=5.0,
        ),
        conformal_observations=conformal,
        drift_observations=drift_observations,
        drift_policies=drift_policies,
        paired_loss_observations=paired,
        sequential_comparison_policy=SequentialComparisonPolicy(
            alpha=0.05,
            minimum_samples=20,
            loss_lower_bound=0.0,
            loss_upper_bound=1.0,
        ),
        offline_model_set=frozenset({"champion", "challenger"}),
        live_execution_metrics=LiveExecutionMetrics(
            observation_count=100,
            realized_net_alpha=0.02,
            reference_net_alpha=0.02,
            mean_cost_error_bps=1.0,
            capacity_ratio_to_approved=1.0,
        ),
        stress_capacity_qualification=StressCapacityQualification(
            qualification_state="STRESS_RESILIENT",
            reverse_stress_distance=2.0,
            capacity_limit_ratio=1.0,
        ),
        rollback_policy=RollbackPolicy(minimum_live_observations=20),
        stage_execution_records=tuple(stage_records),
        reality_gap_policy=RealityGapPolicy(minimum_live_pairs=5),
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.bundle import (
        materialized_inputs_sha256,
    )
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.canonical import payload_sha256

    source_hashes = (
        upstream.foundation_bundle.content_sha256,
        upstream.backtest_metrics_bundle.content_sha256,
        upstream.robustness_stress_bundle.content_sha256,
    )
    receipt_values = {
        "receipt_id": "s7-materialization-receipt",
        "run_id": header.run_id,
        "cycle_id": header.cycle_id,
        "source_bundle_sha256s": source_hashes,
        "materialized_payload_sha256": materialized_inputs_sha256(request_values),
        "producer_module_id": "P9.S7.MATERIALIZER",
    }
    receipt = S7MaterializationReceipt(
        **receipt_values,
        receipt_sha256=payload_sha256(receipt_values),
    )
    return S7ExecutionRequest(
        **request_values,
        materialization_receipt=receipt,
    )


@pytest.fixture()
def full_request(base_time, header, upstream):
    return make_execution_request(base_time, header, upstream)
