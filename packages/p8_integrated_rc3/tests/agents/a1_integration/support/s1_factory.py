from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, raw_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import (
    ComponentQualificationStatus,
    ConfidenceState,
    ExerciseStyle,
    FeedbackEffectType,
    FeedbackRecommendationStatus,
    HorizonUnit,
    P7TerminalState,
    PositionSide,
    ProbabilityMeasure,
    RuntimeMode,
    ScoreSemantics,
    SettlementType,
)
from quant_pipeline.phase_08_contracts.p5 import HorizonSpec, P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import (
    CandidateLegV1,
    P6CandidateEconomicPackageV1,
    UnitEconomicsV1,
)
from quant_pipeline.phase_08_contracts.p7 import (
    ComparisonGroupRecord,
    P7RankingHandoffV1,
    P7TerminalCandidateRecord,
    RankedCandidateRecord,
)
from quant_pipeline.phase_08_contracts.p9 import (
    LiquidityHaircutFeedback,
    LiquidityHaircutPayload,
    NumericAuthorizationBound,
    P0PolicyAuthorizationV1,
    P9FeedbackRecommendationV1,
)
from quant_pipeline.phase_08_contracts.state import (
    AccountSnapshot,
    CashBalance,
    MarginBalance,
    PortfolioStateProjection,
    PositionRecord,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import (
    InMemoryArtifactStore,
    InMemoryIdempotencyStore,
    StaticAccountSnapshotAdapter,
    StaticPortfolioStateReader,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import S1Ports, S1RunRequest
from quant_pipeline.phase_08_portfolio_control.s01_boundary.context import S1ExecutionContext


BASE = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
P8_DECISION = BASE
P8_CUTOFF = BASE - timedelta(minutes=5)
P7_DECISION = BASE - timedelta(minutes=5)
P7_COMPUTED = BASE - timedelta(minutes=4)
P7_RECORDED = BASE - timedelta(minutes=3)
P7_AVAILABLE = BASE - timedelta(minutes=2)


@dataclass(frozen=True)
class FullFixture:
    request: S1RunRequest
    ports: S1Ports
    artifact_store: InMemoryArtifactStore
    p6_ref: ArtifactReference | None
    p5_ref: ArtifactReference | None
    portfolio_state: PortfolioStateProjection
    account_snapshot: AccountSnapshot | None


def context(mode: RuntimeMode = RuntimeMode.BACKTEST) -> S1ExecutionContext:
    return S1ExecutionContext(
        run_id="run-001",
        cycle_id="cycle-010",
        cycle_sequence=10,
        decision_time=P8_DECISION,
        market_cutoff_at=P8_CUTOFF,
        computed_at=P8_DECISION + timedelta(seconds=1),
        runtime_mode=mode,
    )


def raw_ref(
    artifact_id: str,
    artifact_type: str,
    raw: bytes,
    *,
    available_at: datetime = P7_AVAILABLE,
    schema_version: str = "1.0.0",
    contract_version: str = "1.0.0",
    relationship_type: str | None = None,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        schema_version=schema_version,
        contract_version=contract_version,
        content_sha256=raw_sha256(raw),
        available_at=available_at,
        relationship_type=relationship_type,
    )


def finalize_hash(model):
    digest = canonical_sha256(model, exclude_keys=frozenset({"content_sha256"}))
    return model.model_copy(update={"content_sha256": digest})


def rehash_p7_payload(payload: dict[str, object]) -> bytes:
    import json

    payload["content_sha256"] = "0" * 64
    provisional_raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    model = P7RankingHandoffV1.model_validate_json(provisional_raw, strict=True)
    payload["content_sha256"] = canonical_sha256(
        model, exclude_keys=frozenset({"content_sha256"})
    )
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_candidate_artifacts(candidate_id: str = "cand-1") -> tuple[dict[str, bytes], ArtifactReference, ArtifactReference]:
    artifacts: dict[str, bytes] = {}

    instrument_raw = b'{"instrument_id":"OPT-ABC-100-C","version":"1"}'
    instrument_ref = raw_ref("instrument-master-opt-abc", "P2_INSTRUMENT_MASTER", instrument_raw)
    artifacts[instrument_ref.artifact_id] = instrument_raw

    forecast_raw = b'{"distribution":"empirical","target":"ABC_RETURN"}'
    forecast_ref = raw_ref("p5-forecast-dist-1", "P5_FORECAST_DISTRIBUTION", forecast_raw)
    artifacts[forecast_ref.artifact_id] = forecast_raw

    calibration_raw = b'{"status":"CALIBRATED","window":"W1"}'
    calibration_ref = raw_ref("p5-calibration-1", "P5_CALIBRATION", calibration_raw)
    artifacts[calibration_ref.artifact_id] = calibration_raw

    view_raw = b'{"view_id":"view-1","schema":"P4_VIEW_V1"}'
    view_ref = raw_ref("p4-view-1", "P4_VIEW", view_raw)
    artifacts[view_ref.artifact_id] = view_raw

    p5 = P5BeliefEvidenceBundleV1(
        belief_state_id="belief-1",
        target_id="ABC_RETURN",
        underlying_or_factor_id="ABC",
        forecast_horizon=HorizonSpec(value=24, unit=HorizonUnit.HOURS),
        as_of_time=P8_CUTOFF - timedelta(minutes=5),
        decision_time=P7_DECISION - timedelta(minutes=1),
        resolver_id="resolver-1",
        model_artifact_id="model-1",
        probability_measure=ProbabilityMeasure.PHYSICAL,
        forecast_distribution_ref=forecast_ref,
        calibration_ref=calibration_ref,
        view_refs=(view_ref,),
    )
    p5_raw = p5.model_dump_json().encode("utf-8")
    p5_ref = raw_ref(
        "p5-belief-bundle-1",
        "P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1",
        p5_raw,
        contract_version="P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1",
    )
    artifacts[p5_ref.artifact_id] = p5_raw

    leg = CandidateLegV1(
        instrument_id="OPT-ABC-100-C",
        instrument_type="OPTION",
        side=PositionSide.LONG,
        unit_quantity=Decimal("1"),
        contract_multiplier=Decimal("100"),
        strike=Decimal("100"),
        expiration=BASE + timedelta(days=30),
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
        contract_valid_from=BASE - timedelta(days=1),
        contract_valid_until=BASE + timedelta(days=30),
        instrument_master_ref=instrument_ref,
    )
    p6 = P6CandidateEconomicPackageV1(
        candidate_id=candidate_id,
        canonical_candidate_id=f"canonical-{candidate_id}",
        candidate_family="LONG_CALL",
        objective_family="DIRECTIONAL_UPSIDE",
        unit_definition="one option contract",
        currency="USD",
        lot_size=Decimal("1"),
        quantity_increment=Decimal("1"),
        legs=(leg,),
        unit_economics=UnitEconomicsV1(
            entry_cost_status=ComponentQualificationStatus.QUALIFIED,
            payoff_status=ComponentQualificationStatus.QUALIFIED,
            maximum_loss_status=ComponentQualificationStatus.QUALIFIED,
            liquidity_status=ComponentQualificationStatus.QUALIFIED,
            lifecycle_status=ComponentQualificationStatus.QUALIFIED,
            unit_entry_cost=Decimal("250"),
            unit_maximum_loss=Decimal("250"),
            margin_per_unit=Decimal("250"),
            liquidity_capacity_units=Decimal("50"),
        ),
        p5_belief_bundle_ref=p5_ref,
        lineage_refs=(view_ref,),
    )
    p6_raw = p6.model_dump_json().encode("utf-8")
    p6_ref = raw_ref(
        "p6-candidate-package-1",
        "P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
        p6_raw,
        contract_version="P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
    )
    artifacts[p6_ref.artifact_id] = p6_raw
    return artifacts, p6_ref, p5_ref


def make_handoff_bytes(
    *,
    ranked: bool = True,
    p6_ref: ArtifactReference | None = None,
    candidate_id: str = "cand-1",
) -> bytes:
    decision_trace_raw = b'{"candidate_id":"cand-1","trace":"ranked"}'
    decision_trace_ref = raw_ref("p7-decision-trace-1", "P7_DECISION_TRACE", decision_trace_raw)
    if ranked:
        assert p6_ref is not None
        ranked_rows = (
            RankedCandidateRecord(
                candidate_id=candidate_id,
                canonical_candidate_id=f"canonical-{candidate_id}",
                comparison_group_id="group-1",
                rank=1,
                score_semantics=ScoreSemantics.ORDINAL,
                confidence_state=ConfidenceState.UNCALIBRATED,
                p6_economic_package_ref=p6_ref,
                decision_trace_ref=decision_trace_ref,
            ),
        )
        abstained_rows: tuple[P7TerminalCandidateRecord, ...] = ()
        comparison_groups = (
            ComparisonGroupRecord(
                comparison_group_id="group-1",
                objective_family="DIRECTIONAL_UPSIDE",
                underlying_scope=("ABC",),
                horizon_scope="24H",
                member_candidate_ids=(candidate_id,),
                comparability_policy_id="comparability-v1",
            ),
        )
    else:
        ranked_rows = ()
        abstained_rows = (
            P7TerminalCandidateRecord(
                candidate_id=candidate_id,
                terminal_state=P7TerminalState.ABSTAINED,
                reason_codes=("CONFIDENCE_UNAVAILABLE",),
            ),
        )
        comparison_groups = ()
    provisional = P7RankingHandoffV1(
        handoff_id="p7-handoff-1",
        contract_version="P7_TO_P8_RANKING_HANDOFF_V1",
        schema_version="1.0.0",
        producer_phase="P7",
        producer_release="0.30.0",
        run_id="run-001",
        cycle_id="cycle-010",
        decision_time=P7_DECISION,
        market_cutoff_at=P8_CUTOFF,
        computed_at=P7_COMPUTED,
        recorded_at=P7_RECORDED,
        available_at=P7_AVAILABLE,
        content_sha256="0" * 64,
        received_candidate_ids=(candidate_id,),
        ranked=ranked_rows,
        abstained=abstained_rows,
        comparison_groups=comparison_groups,
        artifact_refs=(decision_trace_ref,) + (() if p6_ref is None else (p6_ref,)),
    )
    handoff = finalize_hash(provisional)
    return handoff.model_dump_json().encode("utf-8")


def make_portfolio_state() -> tuple[dict[str, bytes], PortfolioStateProjection]:
    event_raw = b'{"event":"INITIAL_STATE","sequence":0}'
    event_ref = raw_ref("event-log-1", "P8_EVENT_LOG", event_raw)
    provisional = PortfolioStateProjection(
        state_id="state-1",
        as_of_time=P8_DECISION - timedelta(seconds=2),
        positions=(
            PositionRecord(
                instrument_id="OPT-ABC-100-C",
                quantity=Decimal("0"),
                contract_multiplier=Decimal("100"),
                currency="USD",
            ),
        ),
        cash=(CashBalance(currency="USD", amount=Decimal("100000")),),
        margin=(MarginBalance(currency="USD", used=Decimal("0"), available=Decimal("100000")),),
        event_log_ref=event_ref,
        replay_hash="1" * 64,
        content_sha256="0" * 64,
    )
    state = finalize_hash(provisional)
    return {event_ref.artifact_id: event_raw}, state


def make_account_snapshot(state: PortfolioStateProjection) -> AccountSnapshot:
    provisional = AccountSnapshot(
        account_snapshot_id="account-1",
        as_of_time=state.as_of_time,
        positions=state.positions,
        cash=state.cash,
        margin=state.margin,
        collateral=state.collateral,
        open_orders=state.open_orders,
        content_sha256="0" * 64,
    )
    return finalize_hash(provisional)


def make_feedback_artifacts() -> tuple[dict[str, bytes], ArtifactReference]:
    recommendation = P9FeedbackRecommendationV1(
        recommendation_id="recommendation-1",
        feedback_id="feedback-1",
        target_policy_id="liquidity-policy-1",
        effect_type=FeedbackEffectType.LIQUIDITY_HAIRCUT_FEEDBACK,
        status=FeedbackRecommendationStatus.PROMOTED,
        source_cycle_sequence=9,
        available_at=P7_AVAILABLE,
    )
    recommendation_raw = recommendation.model_dump_json().encode("utf-8")
    recommendation_ref = raw_ref("p9-recommendation-1", "P9_FEEDBACK_RECOMMENDATION_V1", recommendation_raw)

    authorization = P0PolicyAuthorizationV1(
        authorization_id="authorization-1",
        feedback_id="feedback-1",
        target_policy_id="liquidity-policy-1",
        effect_type=FeedbackEffectType.LIQUIDITY_HAIRCUT_FEEDBACK,
        valid_from_sequence=10,
        expires_after_sequence=12,
        numeric_bounds=(
            NumericAuthorizationBound(
                field_name="haircut_ratio",
                minimum=Decimal("0"),
                maximum=Decimal("0.50"),
            ),
        ),
        available_at=P7_AVAILABLE,
    )
    authorization_raw = authorization.model_dump_json().encode("utf-8")
    authorization_ref = raw_ref("p0-authorization-1", "P0_POLICY_AUTHORIZATION_V1", authorization_raw)

    provisional = LiquidityHaircutFeedback(
        feedback_id="feedback-1",
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
        schema_version="1.0.0",
        source_cycle_id="cycle-009",
        source_cycle_sequence=9,
        target_cycle_id="cycle-010",
        target_cycle_sequence=10,
        target_policy_id="liquidity-policy-1",
        effect_type=FeedbackEffectType.LIQUIDITY_HAIRCUT_FEEDBACK,
        p9_recommendation_ref=recommendation_ref,
        p0_authorization_ref=authorization_ref,
        effective_from_sequence=10,
        expires_after_sequence=12,
        idempotency_key="feedback-1:cycle-010",
        available_at=P7_AVAILABLE,
        content_sha256="0" * 64,
        payload=LiquidityHaircutPayload(instrument_family="OPTION", haircut_ratio=Decimal("0.25")),
    )
    feedback = finalize_hash(provisional)
    feedback_raw = feedback.model_dump_json().encode("utf-8")
    feedback_ref = raw_ref(
        "feedback-1.json",
        "P9_TO_P8_PROMOTED_FEEDBACK_V1",
        feedback_raw,
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
    )
    artifacts = {
        recommendation_ref.artifact_id: recommendation_raw,
        authorization_ref.artifact_id: authorization_raw,
        feedback_ref.artifact_id: feedback_raw,
    }
    return artifacts, feedback_ref


def full_fixture(
    *,
    ranked: bool = True,
    mode: RuntimeMode = RuntimeMode.BACKTEST,
    include_external_account: bool | None = None,
    include_feedback: bool = False,
) -> FullFixture:
    artifacts: dict[str, bytes] = {}
    p6_ref = None
    p5_ref = None
    if ranked:
        candidate_artifacts, p6_ref, p5_ref = build_candidate_artifacts()
        artifacts.update(candidate_artifacts)
    handoff_bytes = make_handoff_bytes(ranked=ranked, p6_ref=p6_ref)
    # P7 supporting evidence is content-addressed and must be resolvable by M03.
    artifacts["p7-decision-trace-1"] = b'{"candidate_id":"cand-1","trace":"ranked"}'

    state_artifacts, state = make_portfolio_state()
    artifacts.update(state_artifacts)
    if include_external_account is None:
        include_external_account = mode is not RuntimeMode.BACKTEST
    account = make_account_snapshot(state) if include_external_account else None

    market_raw = b'{"snapshot_id":"market-1","as_of_time":"2026-08-03T17:55:00Z"}'
    market_ref = raw_ref(
        "market-snapshot-1",
        "P2_TO_P8_MARKET_EXECUTION_SNAPSHOT_V1",
        market_raw,
        available_at=P7_AVAILABLE,
        contract_version="P2_TO_P8_MARKET_EXECUTION_SNAPSHOT_V1",
    )
    artifacts[market_ref.artifact_id] = market_raw

    feedback_refs: tuple[ArtifactReference, ...] = ()
    if include_feedback:
        feedback_artifacts, feedback_ref = make_feedback_artifacts()
        artifacts.update(feedback_artifacts)
        feedback_refs = (feedback_ref,)

    artifact_store = InMemoryArtifactStore(artifacts)
    ports = S1Ports(
        artifact_store=artifact_store,
        idempotency_store=InMemoryIdempotencyStore(),
        portfolio_state_reader=StaticPortfolioStateReader(state),
        account_snapshot_port=StaticAccountSnapshotAdapter(account),
    )
    request = S1RunRequest(
        p7_handoff_bytes=handoff_bytes,
        feedback_refs=feedback_refs,
        market_snapshot_ref=market_ref,
        context=context(mode),
    )
    return FullFixture(
        request=request,
        ports=ports,
        artifact_store=artifact_store,
        p6_ref=p6_ref,
        p5_ref=p5_ref,
        portfolio_state=state,
        account_snapshot=account,
    )
