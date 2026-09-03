from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s07_prospective_validation.canonical import file_sha256
from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    ArtifactReference,
    Availability,
    ConsumerReceipt,
    IntegrityEnvelope,
    ModuleExecutionReceipt,
    ModuleStatus,
    S7SubphaseExecutionReceipt,
    S7UpstreamReferences,
    validate_reason_code,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.errors import ContractError
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import (
    DecisionKind,
    EvidenceClass,
    IntervalForecast,
    MaturityState,
    NormalForecast,
    OutcomeEvent,
    PointForecast,
    PredictionEvent,
    PrequentialRecord,
    QuantileForecast,
    QuantilePoint,
    build_prequential_stream,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m02_shadow import (
    DeploymentStage,
    PolicyExecutionOutput,
    PolicyRole,
    PolicySpecification,
    build_shadow_execution_plan,
    evaluate_shadow_comparability,
    execute_shadow_plan,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m03_scoring import (
    ScoringPolicy,
    score_prequential_records,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m06_sequential import (
    ComparisonState,
    PairedLossObservation,
    SequentialComparisonPolicy,
    compare_policies_anytime,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m07_rollback import (
    LiveExecutionMetrics,
    LiveHealthState,
    RollbackPolicy,
    StressCapacityQualification,
    evaluate_live_health,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m05_drift import CrossChannelAgreement
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m06_sequential import SequentialModelSet
from quant_pipeline.phase_09.subphases.s07_prospective_validation.runner import _aggregate_subphase_status

pytestmark = pytest.mark.adversarial
H = "0" * 64


def _prediction(base: datetime, event_id: str = "p", forecast=None) -> PredictionEvent:
    return PredictionEvent(
        event_id=event_id,
        cohort_id="c",
        policy_id="champion",
        policy_version="1",
        target_id="t",
        horizon_id="1d",
        issued_at=base,
        information_set_hash=sha256(event_id.encode()).hexdigest(),
        forecast=forecast or PointForecast(value=0.2),
        decision_kind=DecisionKind.ACTION,
        action_id="a",
    )


def _outcome(base: datetime, event_id: str = "p", outcome_id: str = "o", value=0.4, supersedes=None):
    return OutcomeEvent(
        outcome_id=outcome_id,
        prediction_event_id=event_id,
        observed_at=base + timedelta(days=1),
        available_at=base + timedelta(days=1, minutes=1),
        maturity_state=MaturityState.MATURED,
        evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        value=value,
        vintage_id=outcome_id,
        supersedes_outcome_id=supersedes,
    )


def _module_receipt(module_id: str, status: ModuleStatus, outputs=("out",), reasons=()):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return ModuleExecutionReceipt(
        module_id=module_id,
        status=status,
        input_artifact_ids=("in",),
        output_artifact_ids=outputs,
        reason_codes=reasons,
        started_at=now,
        completed_at=now,
        diagnostics_sha256=H,
        integrity=IntegrityEnvelope(payload_sha256=H),
    )


def test_contract_clock_and_receipt_invariants(tmp_path: Path):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    common = dict(
        artifact_id="a", artifact_type="t", artifact_schema_name="s",
        artifact_schema_version="1", artifact_schema_sha256=H, content_sha256=H,
        producer_module_id="P9.S6.M08", run_id="r", cycle_id="c", uri="artifact://a",
    )
    with pytest.raises(ValidationError):
        ArtifactReference(**common, available_at=base, decision_time=base - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        ArtifactReference(**common, available_at=base, computed_at=base - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        ArtifactReference(**common, available_at=base, decision_time=base, maturity_at=base - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        ArtifactReference(**common, available_at=base.astimezone(timezone(timedelta(hours=2))))

    with pytest.raises(ValidationError):
        ConsumerReceipt(
            consumer_module_id="P9.S7.M01", source_contract_name="x", source_contract_version="1",
            source_bundle_sha256=H, input_ref_ids=("a",), accepted_ref_ids=("a",), rejected_ref_ids=("a",),
            reason_codes=("P9_X",),
        )
    with pytest.raises(ValidationError):
        ConsumerReceipt(
            consumer_module_id="P9.S7.M01", source_contract_name="x", source_contract_version="1",
            source_bundle_sha256=H, input_ref_ids=("a", "b"), accepted_ref_ids=("a",),
        )
    with pytest.raises(ValidationError):
        ConsumerReceipt(
            consumer_module_id="P9.S7.M01", source_contract_name="x", source_contract_version="1",
            source_bundle_sha256=H, input_ref_ids=("a",), accepted_ref_ids=(), rejected_ref_ids=("a",),
        )

    with pytest.raises(ValidationError):
        _module_receipt("P9.S7.M01", ModuleStatus.SUCCESS, outputs=())
    with pytest.raises(ValidationError):
        _module_receipt("P9.S7.M01", ModuleStatus.FAILED, reasons=())
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        ModuleExecutionReceipt(
            module_id="P9.S7.M01", status=ModuleStatus.INVALID, input_artifact_ids=(), output_artifact_ids=(),
            reason_codes=("P9_X",), started_at=now, completed_at=now-timedelta(seconds=1),
            diagnostics_sha256=H, integrity=IntegrityEnvelope(payload_sha256=H),
        )
    with pytest.raises(ValidationError):
        ModuleExecutionReceipt(
            module_id="P9.S7.M01", status=ModuleStatus.INVALID, input_artifact_ids=(), output_artifact_ids=(),
            reason_codes=("P9_X",), started_at=now.replace(tzinfo=None), completed_at=now,
            diagnostics_sha256=H, integrity=IntegrityEnvelope(payload_sha256=H),
        )

    r1 = _module_receipt("P9.S7.M01", ModuleStatus.SUCCESS)
    rf = _module_receipt("P9.S7.M02", ModuleStatus.FAILED, outputs=(), reasons=("P9_X",))
    with pytest.raises(ValidationError):
        S7SubphaseExecutionReceipt(expected_module_ids=("P9.S7.M01", "P9.S7.M02"), module_receipts=(r1, r1), status=ModuleStatus.SUCCESS, output_artifact_ids=("out",), integrity=IntegrityEnvelope(payload_sha256=H))
    with pytest.raises(ValidationError):
        S7SubphaseExecutionReceipt(expected_module_ids=("P9.S7.M01", "P9.S7.M02"), module_receipts=(r1,), status=ModuleStatus.SUCCESS, output_artifact_ids=("out",), integrity=IntegrityEnvelope(payload_sha256=H))
    with pytest.raises(ValidationError):
        S7SubphaseExecutionReceipt(expected_module_ids=("P9.S7.M01", "P9.S7.M02"), module_receipts=(r1, rf), status=ModuleStatus.SUCCESS, output_artifact_ids=("out",), integrity=IntegrityEnvelope(payload_sha256=H))
    with pytest.raises(ValidationError):
        S7SubphaseExecutionReceipt(expected_module_ids=("P9.S7.M01", "P9.S7.M02"), module_receipts=(r1, rf), status=ModuleStatus.LIMITED, output_artifact_ids=("out",), integrity=IntegrityEnvelope(payload_sha256=H))

    assert validate_reason_code("P9_VALID_CODE") == "P9_VALID_CODE"
    with pytest.raises(ValueError):
        validate_reason_code("bad-code")
    f = tmp_path / "x"; f.write_bytes(b"abc")
    assert file_sha256(f) == sha256(b"abc").hexdigest()


def test_upstream_receipt_coverage_and_status_aggregation(upstream):
    with pytest.raises(ValidationError):
        S7UpstreamReferences(
            foundation_bundle=upstream.foundation_bundle,
            backtest_metrics_bundle=upstream.backtest_metrics_bundle,
            robustness_stress_bundle=upstream.robustness_stress_bundle,
            consumer_receipts=upstream.consumer_receipts[:1],
        )
    assert _aggregate_subphase_status((_module_receipt("P9.S7.M01", ModuleStatus.SUCCESS),)) is ModuleStatus.SUCCESS
    assert _aggregate_subphase_status((_module_receipt("P9.S7.M01", ModuleStatus.LIMITED),)) is ModuleStatus.LIMITED
    assert _aggregate_subphase_status((_module_receipt("P9.S7.M01", ModuleStatus.INVALID, outputs=(), reasons=("P9_X",)),)) is ModuleStatus.INVALID
    assert _aggregate_subphase_status((_module_receipt("P9.S7.M01", ModuleStatus.FAILED, outputs=(), reasons=("P9_X",)),)) is ModuleStatus.FAILED
    assert _aggregate_subphase_status((_module_receipt("P9.S7.M01", ModuleStatus.INSUFFICIENT_EVIDENCE, outputs=("x",)),)) is ModuleStatus.INSUFFICIENT_EVIDENCE


def test_prequential_validation_and_revision_failures(base_time):
    with pytest.raises(ValidationError):
        QuantileForecast(points=(QuantilePoint(quantile=0.5, value=1.0),))
    with pytest.raises(ValidationError):
        QuantileForecast(points=(QuantilePoint(quantile=0.8, value=1.0), QuantilePoint(quantile=0.2, value=2.0)))
    with pytest.raises(ValidationError):
        IntervalForecast(lower=2.0, upper=1.0, nominal_coverage=0.9)
    with pytest.raises(ValidationError):
        _prediction(base_time.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        PredictionEvent(**{**_prediction(base_time).model_dump(), "decision_kind": DecisionKind.NO_ACTION, "action_id": "bad"})
    with pytest.raises(ValidationError):
        OutcomeEvent(**{**_outcome(base_time).model_dump(), "available_at": base_time})
    with pytest.raises(ValidationError):
        OutcomeEvent(**{**_outcome(base_time).model_dump(), "maturity_state": MaturityState.MATURED, "value": None})
    with pytest.raises(ValidationError):
        OutcomeEvent(**{**_outcome(base_time).model_dump(), "maturity_state": MaturityState.NOT_MATURED, "value": 1.0})

    pred = _prediction(base_time)
    out = _outcome(base_time)
    with pytest.raises(ValidationError):
        PrequentialRecord(prediction=pred, outcomes=(OutcomeEvent(**{**out.model_dump(), "prediction_event_id": "other"}),), active_outcome_id=None, record_sha256=H)
    with pytest.raises(ValidationError):
        PrequentialRecord(prediction=pred, outcomes=(out, out), active_outcome_id=out.outcome_id, record_sha256=H)
    with pytest.raises(ValidationError):
        PrequentialRecord(prediction=pred, outcomes=(out,), active_outcome_id="missing", record_sha256=H)

    with pytest.raises(ContractError):
        build_prequential_stream((pred,), (_outcome(base_time, outcome_id="o1"), _outcome(base_time, outcome_id="o2")))
    with pytest.raises(ContractError):
        build_prequential_stream((pred,), (_outcome(base_time, outcome_id="o1", supersedes="o2"), _outcome(base_time, outcome_id="o2", supersedes="o1")))
    with pytest.raises(ContractError):
        build_prequential_stream((_prediction(base_time, "p"), _prediction(base_time+timedelta(seconds=1), "p")), ())


def test_shadow_failure_and_contract_paths(base_time):
    stream = build_prequential_stream((_prediction(base_time),), ())
    champion = PolicySpecification(policy_id="champion", policy_version="1", role=PolicyRole.CHAMPION, code_sha256=H, resource_budget_units=1, seed_entropy=1, authorized_stage=DeploymentStage.SHADOW_ONLY)
    challenger = PolicySpecification(policy_id="challenger", policy_version="1", role=PolicyRole.CHALLENGER, code_sha256=H, resource_budget_units=1, seed_entropy=2, authorized_stage=DeploymentStage.SHADOW_ONLY)
    with pytest.raises(ValidationError):
        PolicySpecification(policy_id="x", policy_version="1", role=PolicyRole.CHALLENGER, code_sha256=H, resource_budget_units=1, seed_entropy=1, authorized_stage=DeploymentStage.LIMITED_CAPITAL)
    with pytest.raises(ContractError):
        build_shadow_execution_plan(stream.records, challenger, ())
    with pytest.raises(ContractError):
        build_shadow_execution_plan(stream.records, champion, (champion,))
    with pytest.raises(ContractError):
        build_shadow_execution_plan(stream.records, champion, (PolicySpecification(**{**challenger.model_dump(), "policy_id": "champion"}),))
    with pytest.raises(ContractError):
        build_shadow_execution_plan(stream.records, champion, (challenger,), frozenset({"champion"}))

    plan = build_shadow_execution_plan(stream.records, champion, (challenger,))
    failed = execute_shadow_plan(plan, lambda _: (_ for _ in ()).throw(RuntimeError("boom")), lambda: base_time)
    assert all(item.execution_status == "FAILED_INTERNAL" for item in failed)
    with pytest.raises(ContractError):
        execute_shadow_plan(plan, lambda entry: PolicyExecutionOutput(cohort_id=entry.cohort_id, prediction_event_id="wrong", policy_id=entry.policy_id, policy_version=entry.policy_version, information_set_hash=entry.information_set_hash, stage=entry.stage, started_at=base_time, completed_at=base_time, execution_status="FAILED", resource_units_used=0), lambda: base_time)
    with pytest.raises(ContractError):
        execute_shadow_plan(plan, lambda entry: PolicyExecutionOutput(cohort_id=entry.cohort_id, prediction_event_id=entry.prediction_event_id, policy_id=entry.policy_id, policy_version=entry.policy_version, information_set_hash="1"*64, stage=entry.stage, started_at=base_time, completed_at=base_time, execution_status="FAILED", resource_units_used=0), lambda: base_time)
    with pytest.raises(ContractError):
        execute_shadow_plan(plan, lambda entry: PolicyExecutionOutput(cohort_id=entry.cohort_id, prediction_event_id=entry.prediction_event_id, policy_id=entry.policy_id, policy_version=entry.policy_version, information_set_hash=entry.information_set_hash, stage=entry.stage, started_at=base_time, completed_at=base_time, execution_status="FAILED", resource_units_used=2), lambda: base_time)
    receipt = evaluate_shadow_comparability(plan, failed[:1])
    assert receipt.incomplete_cohort_count == 1
    with pytest.raises(ContractError):
        evaluate_shadow_comparability(plan, (failed[0], failed[0]))


def test_scoring_all_forecast_families_and_nonmature(base_time):
    forecasts = (
        PointForecast(value=0.0),
        QuantileForecast(points=(QuantilePoint(quantile=0.25, value=-1.0), QuantilePoint(quantile=0.75, value=1.0))),
        IntervalForecast(lower=-1.0, upper=1.0, nominal_coverage=0.8),
        NormalForecast(mean=0.0, standard_deviation=1.0),
    )
    records=[]
    for i, fc in enumerate(forecasts):
        p=_prediction(base_time-timedelta(days=2), f"p{i}", fc)
        records.extend(build_prequential_stream((p,), (_outcome(p.issued_at, p.event_id, f"o{i}", 2.0),)).records)
    pending=_prediction(base_time, "pending", PointForecast(value=0.0))
    records.extend(build_prequential_stream((pending,), ()).records)
    result=score_prequential_records(tuple(records), ScoringPolicy(minimum_calibration_count=2))
    names={x.score_name for x in result.score_records}
    assert {"ABSOLUTE_ERROR", "MEAN_PINBALL", "INTERVAL_SCORE", "NORMAL_CRPS"} <= names


def test_sequential_invalid_and_offline_paths():
    policy=SequentialComparisonPolicy(alpha=0.05, minimum_samples=2, loss_lower_bound=0.0, loss_upper_bound=1.0, maximum_family_size=1)
    obs=(PairedLossObservation(cohort_id="c", prediction_event_id="p", champion_policy_id="champ", challenger_policy_id="chall", champion_loss=0.2, challenger_loss=0.3),)
    result=compare_policies_anytime(obs, policy, frozenset({"champ"}))
    assert result.comparisons[0].state is ComparisonState.COMPARISON_INVALID
    bad=(PairedLossObservation(cohort_id="c", prediction_event_id="p", champion_policy_id="champ", challenger_policy_id="chall", champion_loss=-2.0, challenger_loss=2.0),)
    result=compare_policies_anytime(bad, policy)
    assert result.comparisons[0].state is ComparisonState.COMPARISON_INVALID
    with pytest.raises(ValueError):
        compare_policies_anytime(obs+obs, policy)
    with pytest.raises(ValueError):
        compare_policies_anytime(obs+(PairedLossObservation(cohort_id="c2", prediction_event_id="p2", champion_policy_id="other", challenger_policy_id="x", champion_loss=.1, challenger_loss=.2),), SequentialComparisonPolicy(alpha=.05, minimum_samples=2, loss_lower_bound=0., loss_upper_bound=1., maximum_family_size=2))


def test_rollback_sample_alpha_capacity_drift_and_challenger():
    empty_set=SequentialModelSet(champion_policy_id="champ", retained_policy_ids=("champ",), comparisons=(), result_sha256=H)
    no_drift=CrossChannelAgreement(alerted_channel_ids=(), confirmed=False, hard_breach_present=False, agreement_ratio=0.0)
    stress=StressCapacityQualification(qualification_state="OK")
    policy=RollbackPolicy(minimum_live_observations=10, alpha_decay_threshold=-0.01)
    insufficient=evaluate_live_health(LiveExecutionMetrics(observation_count=2, realized_net_alpha=None, reference_net_alpha=None, mean_cost_error_bps=None), no_drift, empty_set, stress, policy)
    assert insufficient.state is LiveHealthState.INSUFFICIENT_LIVE_EVIDENCE
    watch=evaluate_live_health(LiveExecutionMetrics(observation_count=20, realized_net_alpha=.01, reference_net_alpha=.01, mean_cost_error_bps=6.0, capacity_ratio_to_approved=.7), no_drift, empty_set, stress, policy)
    assert watch.state is LiveHealthState.WATCH
    degraded=evaluate_live_health(LiveExecutionMetrics(observation_count=20, realized_net_alpha=-.1, reference_net_alpha=.1, mean_cost_error_bps=0.0, capacity_ratio_to_approved=1.0), CrossChannelAgreement(alerted_channel_ids=("x",), confirmed=True, hard_breach_present=False, agreement_ratio=1.0), empty_set, stress, policy)
    assert degraded.state is LiveHealthState.ROLLBACK_RECOMMENDED
