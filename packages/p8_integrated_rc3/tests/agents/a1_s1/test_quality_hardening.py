from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_contracts.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
    canonical_sha256,
    finalize_content_hash,
    to_canonical_data,
)
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import (
    ComponentQualificationStatus,
    ExerciseStyle,
    FeedbackEffectType,
    FeedbackRecommendationStatus,
    HorizonUnit,
    PositionSide,
    ProbabilityMeasure,
    ReceiptStatus,
    RuntimeMode,
    SettlementType,
)
from quant_pipeline.phase_08_contracts.p5 import HorizonSpec, P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import CandidateLegV1, UnitEconomicsV1
from quant_pipeline.phase_08_contracts.p7 import (
    ComparisonGroupRecord,
    P7RankingHandoffV1,
    RankedCandidateRecord,
)
from quant_pipeline.phase_08_contracts.p9 import (
    AllowedValuesAuthorizationBound,
    ExecutionPolicyFeedback,
    ExecutionPolicyPayload,
    P0PolicyAuthorizationV1,
    P9FeedbackRecommendationV1,
)
from quant_pipeline.phase_08_contracts.state import (
    AccountSnapshot,
    CashBalance,
    CollateralBalance,
    OpenOrderRecord,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import (
    InMemoryArtifactStore,
    InMemoryIdempotencyStore,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters.debug_filesystem import (
    FileDebugBundleWriter,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters.filesystem import FileArtifactStore
from quant_pipeline.phase_08_portfolio_control.s01_boundary.context import S1ExecutionContext
from quant_pipeline.phase_08_portfolio_control.s01_boundary.debug import S1FailureDebugBundle
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import (
    ExternalSystemError,
    FeedbackAuthorizationError,
    FeedbackOutOfBoundsError,
    HashMismatchError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.module_support import (
    load_json_object,
    read_verified_artifact,
    validate_model_json,
    verify_embedded_canonical_hash,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m04_promoted_portfolio_feedback_loader import (
    run_module as run_m04,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.observability import StructuredModuleLogger
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import (
    ContractCompatibilityPolicy,
    StateReconciliationPolicy,
)

from tests.agents.a1_s1.factories import (
    BASE,
    P7_AVAILABLE,
    context,
    finalize_hash,
    full_fixture,
    raw_ref,
)


def test_canonicalization_handles_supported_edge_types() -> None:
    value = {
        "date": date(2026, 8, 3),
        "datetime": datetime(2026, 8, 3, 15, tzinfo=UTC),
        "decimal": Decimal("1.2300"),
        "zero": Decimal("-0"),
        "bytes": b"\x01\xff",
        "set": {"b", "a"},
        "sequence": (2, 1),
    }
    data = to_canonical_data(value)
    assert data == {
        "bytes": "01ff",
        "date": "2026-08-03",
        "datetime": "2026-08-03T15:00:00.000000Z",
        "decimal": "1.23",
        "sequence": [2, 1],
        "set": ["a", "b"],
        "zero": "0",
    }
    assert canonical_json_bytes(value) == canonical_json_bytes(dict(reversed(tuple(value.items()))))


@pytest.mark.parametrize(
    "value,match",
    [
        (datetime(2026, 8, 3, 12), "naive datetime"),
        (Decimal("NaN"), "non-finite Decimal"),
        (float("inf"), "non-finite float"),
        ({1: "bad"}, "mapping keys"),
        (object(), "unsupported canonical type"),
    ],
)
def test_canonicalization_rejects_unsafe_values(value: object, match: str) -> None:
    with pytest.raises(CanonicalizationError, match=match):
        to_canonical_data(value)


def test_finalize_content_hash_revalidates_model() -> None:
    ref = ArtifactReference(
        artifact_id="a",
        artifact_type="TYPE",
        schema_version="1",
        contract_version="1",
        content_sha256="0" * 64,
        available_at=P7_AVAILABLE,
    )
    finalized = finalize_content_hash(ref)
    assert finalized.content_sha256 == canonical_sha256(finalized, exclude_keys=frozenset({"content_sha256"}))
    with pytest.raises(ValidationError):
        finalize_content_hash(ref, field_name="available_at")


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"run_id": ""}, "run_id"),
        ({"cycle_sequence": -1}, "cycle_sequence"),
        ({"decision_time": datetime(2026, 8, 3, 18)}, "timezone-aware"),
        ({"market_cutoff_at": BASE + timedelta(seconds=1)}, "market_cutoff"),
        ({"computed_at": BASE - timedelta(seconds=1)}, "computed_at"),
    ],
)
def test_context_rejects_invalid_clock_or_identity(kwargs: dict[str, object], match: str) -> None:
    values: dict[str, object] = {
        "run_id": "run",
        "cycle_id": "cycle",
        "cycle_sequence": 1,
        "decision_time": BASE,
        "market_cutoff_at": BASE - timedelta(minutes=1),
        "computed_at": BASE + timedelta(seconds=1),
        "runtime_mode": RuntimeMode.BACKTEST,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=match):
        S1ExecutionContext(**values)  # type: ignore[arg-type]


def test_policy_objects_reject_empty_or_negative_values() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ContractCompatibilityPolicy(accepted_contract_versions=frozenset())
    with pytest.raises(ValueError, match="non-negative"):
        StateReconciliationPolicy(cash_tolerance=Decimal("-0.01"))
    with pytest.raises(ValueError, match="material_discrepancy_limit"):
        StateReconciliationPolicy(material_discrepancy_limit=-1)


def test_module_support_rejects_invalid_json_and_hashes() -> None:
    with pytest.raises(Exception, match="UTF-8 JSON"):
        load_json_object(b"not-json")
    with pytest.raises(Exception, match="root"):
        load_json_object(b"[]")
    with pytest.raises(Exception, match="schema validation"):
        validate_model_json(HorizonSpec, b'{"value":"24","unit":"HOURS"}', label="horizon")
    with pytest.raises(Exception, match="must be present"):
        verify_embedded_canonical_hash({"x": 1})
    with pytest.raises(HashMismatchError):
        verify_embedded_canonical_hash({"content_sha256": "0" * 64, "x": 1})


def test_read_verified_artifact_enforces_port_and_time() -> None:
    raw = b"payload"
    ref = raw_ref("a", "TYPE", raw, available_at=BASE + timedelta(seconds=1))
    with pytest.raises(TemporalIntegrityError):
        read_verified_artifact(InMemoryArtifactStore({"a": raw}), ref, decision_time=BASE)
    ref_now = raw_ref("a", "TYPE", raw)
    with pytest.raises(TypeError, match="does not implement read"):
        read_verified_artifact(object(), ref_now, decision_time=BASE)


def test_inmemory_and_filesystem_artifact_stores_are_content_addressed(tmp_path: Path) -> None:
    raw = b"exact bytes"
    ref = raw_ref("nested/a.json", "TYPE", raw)
    memory = InMemoryArtifactStore()
    memory.put(ref, raw)
    assert memory.read(ref) == raw
    assert memory.export() == {ref.artifact_id: raw}
    with pytest.raises(HashMismatchError):
        memory.put(ref, b"different")
    with pytest.raises(ExternalSystemError, match="not found"):
        memory.read(raw_ref("missing", "TYPE", b"x"))

    path = tmp_path / "nested" / "a.json"
    path.parent.mkdir()
    path.write_bytes(raw)
    store = FileArtifactStore(tmp_path)
    assert store.read(ref) == raw
    escape = raw_ref("../outside", "TYPE", b"x")
    with pytest.raises(ExternalSystemError, match="escapes"):
        store.read(escape)
    with pytest.raises(ExternalSystemError, match="cannot read"):
        store.read(raw_ref("not-there", "TYPE", b"x"))


def test_debug_writer_is_atomic_and_deterministic(tmp_path: Path) -> None:
    bundle = S1FailureDebugBundle(
        module_id="P8.S1.M01",
        error_type="HashMismatchError",
        reason_code="HASH_MISMATCH",
        message="tampered",
        run_id="run",
        cycle_id="cycle",
        cycle_sequence=1,
        decision_time=BASE,
        market_cutoff_at=BASE - timedelta(minutes=1),
        computed_at=BASE + timedelta(seconds=1),
        runtime_mode=RuntimeMode.BACKTEST,
        input_hashes=("1" * 64,),
    )
    writer = FileDebugBundleWriter(tmp_path)
    first = Path(writer.write_failure(bundle))
    second = Path(writer.write_failure(bundle))
    assert first == second
    assert first.read_bytes() == canonical_json_bytes(bundle)
    assert not list(tmp_path.glob("*.tmp"))


def test_structured_logger_emits_all_levels(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("p8-test")
    wrapped = StructuredModuleLogger(logger)
    with caplog.at_level(logging.INFO, logger="p8-test"):
        wrapped.info("info", {"module_id": "M"})
        wrapped.warning("warn", {"reason": "x"})
        wrapped.error("error", {"reason": "y"})
    assert [record.message for record in caplog.records] == ["info", "warn", "error"]
    assert caplog.records[0].p8 == {"module_id": "M"}  # type: ignore[attr-defined]


def _store_feedback_variant(feedback: object, artifacts: dict[str, bytes], artifact_id: str) -> ArtifactReference:
    finalized = finalize_hash(feedback)
    raw = finalized.model_dump_json().encode("utf-8")
    ref = raw_ref(
        artifact_id,
        "P9_TO_P8_PROMOTED_FEEDBACK_V1",
        raw,
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
    )
    artifacts[ref.artifact_id] = raw
    return ref


def test_feedback_can_be_not_effective_yet() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    artifacts = fixture.artifact_store.export()
    original_ref = fixture.request.feedback_refs[0]
    from quant_pipeline.phase_08_contracts.p9 import LiquidityHaircutFeedback

    original = LiquidityHaircutFeedback.model_validate_json(artifacts[original_ref.artifact_id], strict=True)
    changed = original.model_copy(update={"effective_from_sequence": 11, "content_sha256": "0" * 64})
    ref = _store_feedback_variant(changed, artifacts, "feedback-not-effective")
    result = run_m04(
        (ref,),
        store=InMemoryArtifactStore(artifacts),
        idempotency_store=InMemoryIdempotencyStore(),
        context=fixture.request.context,
    )
    assert result.feedback_context.item_receipts[0].status is ReceiptStatus.NOT_EFFECTIVE_YET
    assert not result.feedback_context.applied_feedback


def test_feedback_can_expire_after_its_target_cycle() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    later = S1ExecutionContext(
        run_id="run-001",
        cycle_id="cycle-013",
        cycle_sequence=13,
        decision_time=BASE + timedelta(days=3),
        market_cutoff_at=BASE + timedelta(days=3, minutes=-5),
        computed_at=BASE + timedelta(days=3, seconds=1),
        runtime_mode=RuntimeMode.BACKTEST,
    )
    result = run_m04(
        fixture.request.feedback_refs,
        store=fixture.artifact_store,
        idempotency_store=InMemoryIdempotencyStore(),
        context=later,
    )
    assert result.feedback_context.item_receipts[0].status is ReceiptStatus.EXPIRED


def test_feedback_targeting_future_cycle_is_rejected() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    artifacts = fixture.artifact_store.export()
    original_ref = fixture.request.feedback_refs[0]
    from quant_pipeline.phase_08_contracts.p9 import LiquidityHaircutFeedback

    original = LiquidityHaircutFeedback.model_validate_json(artifacts[original_ref.artifact_id], strict=True)
    changed = original.model_copy(
        update={
            "target_cycle_id": "cycle-011",
            "target_cycle_sequence": 11,
            "effective_from_sequence": 11,
            "expires_after_sequence": 12,
            "content_sha256": "0" * 64,
        }
    )
    ref = _store_feedback_variant(changed, artifacts, "feedback-future")
    with pytest.raises(FeedbackAuthorizationError, match="future cycle"):
        run_m04(
            (ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )


def test_feedback_requires_promoted_recommendation() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    artifacts = fixture.artifact_store.export()
    feedback_ref = fixture.request.feedback_refs[0]
    from quant_pipeline.phase_08_contracts.p9 import LiquidityHaircutFeedback

    feedback = LiquidityHaircutFeedback.model_validate_json(artifacts[feedback_ref.artifact_id], strict=True)
    recommendation = P9FeedbackRecommendationV1.model_validate_json(
        artifacts[feedback.p9_recommendation_ref.artifact_id], strict=True
    )
    changed_rec = recommendation.model_copy(update={"status": FeedbackRecommendationStatus.REJECTED})
    raw = changed_rec.model_dump_json().encode()
    rec_ref = raw_ref("rec-rejected", "P9_FEEDBACK_RECOMMENDATION_V1", raw)
    artifacts[rec_ref.artifact_id] = raw
    changed_feedback = feedback.model_copy(
        update={"p9_recommendation_ref": rec_ref, "content_sha256": "0" * 64}
    )
    changed_ref = _store_feedback_variant(changed_feedback, artifacts, "feedback-rejected-rec")
    with pytest.raises(FeedbackAuthorizationError, match="not PROMOTED"):
        run_m04(
            (changed_ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )


def test_execution_feedback_allowed_values_are_enforced() -> None:
    fixture = full_fixture(ranked=False)
    artifacts = fixture.artifact_store.export()
    recommendation = P9FeedbackRecommendationV1(
        recommendation_id="rec-execution",
        feedback_id="feedback-execution",
        target_policy_id="execution-policy",
        effect_type=FeedbackEffectType.EXECUTION_POLICY_FEEDBACK,
        status=FeedbackRecommendationStatus.PROMOTED,
        source_cycle_sequence=9,
        available_at=P7_AVAILABLE,
    )
    rec_raw = recommendation.model_dump_json().encode()
    rec_ref = raw_ref("rec-execution", "P9_FEEDBACK_RECOMMENDATION_V1", rec_raw)
    authorization = P0PolicyAuthorizationV1(
        authorization_id="auth-execution",
        feedback_id="feedback-execution",
        target_policy_id="execution-policy",
        effect_type=FeedbackEffectType.EXECUTION_POLICY_FEEDBACK,
        valid_from_sequence=10,
        expires_after_sequence=12,
        allowed_values=(
            AllowedValuesAuthorizationBound(field_name="allowed_order_types", allowed_values=("LIMIT",)),
        ),
        available_at=P7_AVAILABLE,
    )
    auth_raw = authorization.model_dump_json().encode()
    auth_ref = raw_ref("auth-execution", "P0_POLICY_AUTHORIZATION_V1", auth_raw)
    provisional = ExecutionPolicyFeedback(
        feedback_id="feedback-execution",
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
        schema_version="1.0.0",
        source_cycle_id="cycle-009",
        source_cycle_sequence=9,
        target_cycle_id="cycle-010",
        target_cycle_sequence=10,
        target_policy_id="execution-policy",
        effect_type=FeedbackEffectType.EXECUTION_POLICY_FEEDBACK,
        p9_recommendation_ref=rec_ref,
        p0_authorization_ref=auth_ref,
        effective_from_sequence=10,
        expires_after_sequence=12,
        idempotency_key="execution-feedback",
        available_at=P7_AVAILABLE,
        content_sha256="0" * 64,
        payload=ExecutionPolicyPayload(
            max_participation_rate=Decimal("0.1"),
            allowed_order_types=("LIMIT", "MARKET"),
        ),
    )
    feedback_ref = _store_feedback_variant(provisional, artifacts, "feedback-execution")
    artifacts[rec_ref.artifact_id] = rec_raw
    artifacts[auth_ref.artifact_id] = auth_raw
    with pytest.raises(FeedbackOutOfBoundsError, match="unauthorized value"):
        run_m04(
            (feedback_ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )


def test_contract_model_validation_branches() -> None:
    with pytest.raises(ValidationError, match="predictive evidence"):
        P5BeliefEvidenceBundleV1(
            belief_state_id="b",
            target_id="t",
            underlying_or_factor_id="u",
            forecast_horizon=HorizonSpec(value=1, unit=HorizonUnit.HOURS),
            as_of_time=BASE,
            decision_time=BASE,
            resolver_id="r",
            model_artifact_id="m",
            probability_measure=ProbabilityMeasure.PHYSICAL,
        )
    with pytest.raises(ValidationError, match="after P5 decision"):
        P5BeliefEvidenceBundleV1(
            belief_state_id="b",
            target_id="t",
            underlying_or_factor_id="u",
            forecast_horizon=HorizonSpec(value=1, unit=HorizonUnit.HOURS),
            as_of_time=BASE + timedelta(seconds=1),
            decision_time=BASE,
            resolver_id="r",
            model_artifact_id="m",
            probability_measure=ProbabilityMeasure.PHYSICAL,
            forecast_distribution_ref=raw_ref("f", "F", b"x"),
        )

    instrument_ref = raw_ref("i", "I", b"i")
    with pytest.raises(ValidationError, match="non-zero"):
        CandidateLegV1(
            instrument_id="i",
            instrument_type="OPTION",
            side=PositionSide.LONG,
            unit_quantity=Decimal("0"),
            contract_multiplier=Decimal("1"),
            expiration=BASE + timedelta(days=1),
            exercise_style=ExerciseStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            contract_valid_from=BASE,
            contract_valid_until=BASE + timedelta(days=1),
            instrument_master_ref=instrument_ref,
        )
    with pytest.raises(ValidationError, match="must not exceed"):
        CandidateLegV1(
            instrument_id="i",
            instrument_type="EQUITY",
            side=PositionSide.LONG,
            unit_quantity=Decimal("1"),
            contract_multiplier=Decimal("1"),
            settlement_type=SettlementType.PHYSICAL,
            contract_valid_from=BASE + timedelta(days=1),
            contract_valid_until=BASE,
            instrument_master_ref=instrument_ref,
        )
    with pytest.raises(ValidationError, match="require expiration"):
        CandidateLegV1(
            instrument_id="i",
            instrument_type="OPTION",
            side=PositionSide.LONG,
            unit_quantity=Decimal("1"),
            contract_multiplier=Decimal("1"),
            exercise_style=ExerciseStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            contract_valid_from=BASE,
            contract_valid_until=BASE + timedelta(days=1),
            instrument_master_ref=instrument_ref,
        )

    with pytest.raises(ValidationError, match="entry cost"):
        UnitEconomicsV1(
            entry_cost_status=ComponentQualificationStatus.QUALIFIED,
            payoff_status=ComponentQualificationStatus.QUALIFIED,
            maximum_loss_status=ComponentQualificationStatus.UNAVAILABLE,
            liquidity_status=ComponentQualificationStatus.UNAVAILABLE,
            lifecycle_status=ComponentQualificationStatus.QUALIFIED,
        )


def test_p7_and_state_model_validation_branches() -> None:
    ref = raw_ref("r", "R", b"r")
    with pytest.raises(ValidationError, match="ORDINAL"):
        RankedCandidateRecord(
            candidate_id="c",
            canonical_candidate_id="cc",
            comparison_group_id="g",
            rank=1,
            score_value=Decimal("1"),
            p6_economic_package_ref=ref,
            decision_trace_ref=ref,
        )
    with pytest.raises(ValidationError, match="unique"):
        ComparisonGroupRecord(
            comparison_group_id="g",
            objective_family="o",
            horizon_scope="1D",
            member_candidate_ids=("c", "c"),
            comparability_policy_id="p",
        )
    with pytest.raises(ValidationError, match="market_cutoff"):
        P7RankingHandoffV1(
            handoff_id="h",
            contract_version="P7_TO_P8_RANKING_HANDOFF_V1",
            schema_version="1.0.0",
            producer_phase="P7",
            producer_release="r",
            run_id="run",
            cycle_id="cycle",
            decision_time=BASE,
            market_cutoff_at=BASE + timedelta(seconds=1),
            computed_at=BASE + timedelta(seconds=2),
            recorded_at=BASE + timedelta(seconds=3),
            available_at=BASE + timedelta(seconds=4),
            content_sha256="0" * 64,
            received_candidate_ids=(),
        )
    with pytest.raises(ValidationError, match="eligible collateral"):
        CollateralBalance(asset_id="a", currency="USD", market_value=Decimal("1"), eligible_value=Decimal("2"))
    with pytest.raises(ValidationError, match="does not conserve"):
        OpenOrderRecord(
            order_id="o",
            instrument_id="i",
            total_quantity=Decimal("10"),
            filled_quantity=Decimal("3"),
            remaining_quantity=Decimal("6"),
            created_at=BASE,
        )
    with pytest.raises(ValidationError, match="unique"):
        AccountSnapshot(
            account_snapshot_id="a",
            as_of_time=BASE,
            cash=(
                CashBalance(currency="USD", amount=Decimal("1")),
                CashBalance(currency="USD", amount=Decimal("2")),
            ),
            content_sha256="0" * 64,
        )


def test_p0_authorization_window_is_validated() -> None:
    with pytest.raises(ValidationError, match="expiry"):
        P0PolicyAuthorizationV1(
            authorization_id="a",
            feedback_id="f",
            target_policy_id="p",
            effect_type=FeedbackEffectType.LIQUIDITY_HAIRCUT_FEEDBACK,
            valid_from_sequence=10,
            expires_after_sequence=9,
            available_at=BASE,
        )
