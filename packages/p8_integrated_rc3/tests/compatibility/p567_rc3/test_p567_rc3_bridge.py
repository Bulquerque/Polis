from __future__ import annotations

import copy
import gzip
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from quant_pipeline.phase_08_contracts.canonical import finalize_content_hash, raw_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import ComponentQualificationStatus, RuntimeMode
from quant_pipeline.phase_08_contracts.state import CashBalance, MarginBalance, PortfolioStateProjection
from quant_pipeline.phase_08_portfolio_control.compatibility.p567_rc3 import (
    P567RC3CompatibilityError,
    adapt_p567_rc3_to_p8,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters.memory import (
    InMemoryIdempotencyStore,
    StaticAccountSnapshotAdapter,
    StaticPortfolioStateReader,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import S1Ports, S1RunRequest, run_s1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.context import S1ExecutionContext
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import (
    S2RunRequest,
    build_s2_input_bundle,
    run_s2,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.context import S2ExecutionContext
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import StaticActionState

FIXTURES = Path(__file__).with_name("fixtures")
SOURCE_DECISION = datetime(2025, 6, 9, 0, 10, tzinfo=UTC)
P8_DECISION = SOURCE_DECISION + timedelta(minutes=1)


def _load(name: str) -> dict[str, object]:
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    assert isinstance(value, dict)
    return value


def _source_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        _load("p5_publication.json.gz"),
        _load("p6_outputs.json.gz"),
        _load("p7_full.json.gz"),
    )


def _adapt(*, p5=None, p6=None, p7=None):
    source_p5, source_p6, source_p7 = _source_inputs()
    return adapt_p567_rc3_to_p8(
        p5_publication=p5 or source_p5,
        p6_outputs=p6 or source_p6,
        p7_result=p7 or source_p7,
        p8_run_id="compat-run",
        p8_cycle_id="compat-cycle",
        p8_decision_time=P8_DECISION,
        market_cutoff_at=SOURCE_DECISION,
        computed_at=SOURCE_DECISION + timedelta(seconds=2),
        recorded_at=SOURCE_DECISION + timedelta(seconds=3),
        available_at=SOURCE_DECISION + timedelta(seconds=4),
    )


def _run_s1_s2(adaptation):
    store = adaptation.build_artifact_store()
    event_raw = b'{"event":"INITIAL_STATE","sequence":0}'
    event_ref = ArtifactReference(
        artifact_id="compat-event-log",
        artifact_type="P8_EVENT_LOG",
        schema_version="1.0.0",
        contract_version="P8_EVENT_LOG_V1",
        content_sha256=raw_sha256(event_raw),
        available_at=SOURCE_DECISION,
    )
    store.put(event_ref, event_raw)
    state = finalize_content_hash(
        PortfolioStateProjection(
            state_id="compat-state",
            as_of_time=P8_DECISION - timedelta(seconds=1),
            cash=(CashBalance(currency="USD", amount=Decimal("100000")),),
            margin=(MarginBalance(currency="USD", used=Decimal("0"), available=Decimal("100000")),),
            event_log_ref=event_ref,
            replay_hash="1" * 64,
            content_sha256="0" * 64,
        )
    )
    market_raw = b'{"snapshot_id":"rc3-market"}'
    market_ref = ArtifactReference(
        artifact_id="compat-market",
        artifact_type="P2_TO_P8_MARKET_EXECUTION_SNAPSHOT_V1",
        schema_version="1.0.0",
        contract_version="P2_TO_P8_MARKET_EXECUTION_SNAPSHOT_V1",
        content_sha256=raw_sha256(market_raw),
        available_at=SOURCE_DECISION,
    )
    store.put(market_ref, market_raw)
    s1_context = S1ExecutionContext(
        run_id="compat-run",
        cycle_id="compat-cycle",
        cycle_sequence=1,
        decision_time=P8_DECISION,
        market_cutoff_at=SOURCE_DECISION,
        computed_at=P8_DECISION + timedelta(seconds=1),
        runtime_mode=RuntimeMode.BACKTEST,
    )
    s1 = run_s1(
        S1RunRequest(
            p7_handoff_bytes=adaptation.handoff_bytes,
            feedback_refs=(),
            market_snapshot_ref=market_ref,
            context=s1_context,
        ),
        S1Ports(
            artifact_store=store,
            idempotency_store=InMemoryIdempotencyStore(),
            portfolio_state_reader=StaticPortfolioStateReader(state),
            account_snapshot_port=StaticAccountSnapshotAdapter(None),
        ),
    )
    s2_input = build_s2_input_bundle(
        validated_handoff=s1.m01.bundle,
        terminal_ledger=s1.m02.ledger,
        resolved_evidence=s1.m03.evidence_index,
        feedback_context=s1.m04.feedback_context,
        current_state=s1.m05.current_state,
        snapshot=s1.snapshot,
    )
    s2 = run_s2(
        S2RunRequest(
            input_bundle=s2_input,
            context=S2ExecutionContext(
                run_id="compat-run",
                cycle_id="compat-cycle",
                decision_time=P8_DECISION,
                computed_at=P8_DECISION + timedelta(seconds=2),
            ),
        )
    )
    return s1, s2


def _rank_all(p7: dict[str, object]) -> dict[str, object]:
    ranked = copy.deepcopy(p7)
    abstained_panel = ranked["finalization"]["s7"]["abstained_candidate_panel"]
    source_rows = abstained_panel["records"]
    ranked_rows = [
        {
            "candidate_id": row["candidate_id"],
            "comparison_group_id": row["comparison_group_id"],
            "rank_position": 1,
            "objective_family": "DIRECTIONAL_UP",
            "underlying_id": "RC3_TEST",
        }
        for row in source_rows
    ]
    abstained_panel["records"] = []
    abstained_panel["record_count"] = 0
    ranked_panel = ranked["finalization"]["s8"]["ranked_strategy_candidate_panel"]
    ranked_panel["records"] = ranked_rows
    ranked_panel["record_count"] = len(ranked_rows)
    return ranked


def test_live_rc3_chain_adapts_to_native_no_action_and_resolves_all_lineage() -> None:
    adaptation = _adapt()
    assert len(adaptation.handoff.received_candidate_ids) == 3
    assert adaptation.handoff.ranked == ()
    assert len(adaptation.handoff.abstained) == 3
    assert len(adaptation.p5_bundles) == 3
    assert len(adaptation.p6_packages) == 3
    assert len(adaptation.s3_beliefs) == 3
    assert all(bundle.probability_measure.value == "PHYSICAL" for bundle in adaptation.p5_bundles.values())
    assert all(package.unit_economics.liquidity_status is ComponentQualificationStatus.UNAVAILABLE for package in adaptation.p6_packages.values())

    s1, s2 = _run_s1_s2(adaptation)
    assert s1.snapshot.no_action is not None
    assert s1.snapshot.actionable_ranked_candidate_ids == ()
    assert all(row.status.value == "RESOLVED" for row in s1.m03.evidence_index.candidates)
    assert s2.bundle.static_action_universe.forwarded_candidate_ids == ()
    assert all(
        row.state is StaticActionState.P7_TERMINAL_PRESERVED
        for row in s2.bundle.static_action_universe.decisions
    )


def test_ranked_rc3_projection_reaches_native_s2_without_cardinal_score_invention() -> None:
    p5, p6, p7 = _source_inputs()
    adaptation = _adapt(p5=p5, p6=p6, p7=_rank_all(p7))
    assert len(adaptation.handoff.ranked) == 3
    assert all(row.score_semantics.value == "ORDINAL" for row in adaptation.handoff.ranked)
    assert all(row.score_value is None for row in adaptation.handoff.ranked)
    assert all(row.confidence_state.value == "UNCALIBRATED" for row in adaptation.handoff.ranked)

    s1, s2 = _run_s1_s2(adaptation)
    assert s1.snapshot.no_action is None
    assert len(s1.snapshot.actionable_ranked_candidate_ids) == 3
    assert len(s2.bundle.static_action_universe.forwarded_candidate_ids) == 3


def test_bridge_preserves_p5_empirical_samples_for_s3() -> None:
    adaptation = _adapt()
    belief = adaptation.s3_beliefs["AAA"]
    assert belief.distribution_type.value == "EMPIRICAL"
    assert belief.factor_ids == ("AAA",)
    assert len(belief.payload.samples) > 100
    assert belief.ood_score == pytest.approx(1.0)
    assert belief.regime_id == "HIGH_VOL"


def test_bridge_fails_closed_when_p6_economics_are_missing() -> None:
    p5, p6, p7 = _source_inputs()
    broken = copy.deepcopy(p6)
    broken["strategy_payoff_panel"]["records"] = broken["strategy_payoff_panel"]["records"][1:]
    with pytest.raises(P567RC3CompatibilityError, match="lacks P6 economics panels"):
        _adapt(p5=p5, p6=broken, p7=p7)


def test_bridge_fails_closed_when_p7_candidate_conservation_does_not_close() -> None:
    p5, p6, p7 = _source_inputs()
    broken = copy.deepcopy(p7)
    broken["finalization"]["s7"]["abstained_candidate_panel"]["records"] = []
    broken["finalization"]["s7"]["final_blocked_candidate_panel"]["records"] = []
    with pytest.raises(P567RC3CompatibilityError, match="did not publish a terminal state"):
        _adapt(p5=p5, p6=p6, p7=broken)


def test_option_candidate_without_rc3_lifecycle_evidence_is_preserved_but_not_forwarded() -> None:
    p5, p6, p7 = _source_inputs()
    projected_p6 = copy.deepcopy(p6)
    candidate = projected_p6["canonical_strategy_candidate_panel"]["records"][0]
    candidate["underlying_id"] = "AAA"
    candidate["legs"] = [
        {
            "currency": "USD",
            "entry_price_reference": "1.25",
            "exchange": "TEST",
            "exercise_style": "EUROPEAN",
            "expiration": "2025-06-10T00:10:00+00:00",
            "instrument_id": "AAA-CALL-100",
            "instrument_type": "OPTION",
            "leg_id": "compat-option-leg",
            "leg_role": "CORE",
            "multiplier": "100",
            "option_type": "CALL",
            "price_selection_method": "ASK",
            "quantity": "1",
            "quote_quality": "AVAILABLE",
            "settlement_type": "CASH",
            "side": "LONG",
            "source_quote_id": "compat-quote",
            "strike": "100",
        }
    ]
    ranked = _rank_all(p7)
    adaptation = _adapt(p5=p5, p6=projected_p6, p7=ranked)
    candidate_id = candidate["candidate_id"]
    assert adaptation.p6_packages[candidate_id].unit_economics.lifecycle_status is ComponentQualificationStatus.UNAVAILABLE

    _, s2 = _run_s1_s2(adaptation)
    decision = next(row for row in s2.bundle.static_action_universe.decisions if row.candidate_id == candidate_id)
    assert decision.state is StaticActionState.STATIC_CAPABILITY_UNSUPPORTED
    assert decision.reason_codes == ("LIFECYCLE_CAPABILITY_UNUSABLE",)


def test_bridge_rejects_publication_after_consumer_decision() -> None:
    p5, p6, p7 = _source_inputs()
    with pytest.raises(P567RC3CompatibilityError, match="bridge clocks"):
        adapt_p567_rc3_to_p8(
            p5_publication=p5,
            p6_outputs=p6,
            p7_result=p7,
            p8_run_id="compat-run",
            p8_cycle_id="compat-cycle",
            p8_decision_time=P8_DECISION,
            market_cutoff_at=SOURCE_DECISION,
            computed_at=P8_DECISION + timedelta(seconds=1),
            recorded_at=P8_DECISION + timedelta(seconds=2),
            available_at=P8_DECISION + timedelta(seconds=3),
        )


def test_bridge_rejects_tampered_p5_embedded_artifact() -> None:
    p5, p6, p7 = _source_inputs()
    broken = copy.deepcopy(p5)
    records = broken["phase5_output_handoff_manifest"]["embedded_v2_artifacts"]["return_distributions"]["records"]
    records[0]["distribution"]["samples"][0] = float(records[0]["distribution"]["samples"][0]) + 1.0
    with pytest.raises(P567RC3CompatibilityError, match="P5 (?:output handoff manifest content_sha256|embedded artifact hash) mismatch"):
        _adapt(p5=broken, p6=p6, p7=p7)


def test_bridge_rejects_missing_p5_pipeline_version() -> None:
    p5, p6, p7 = _source_inputs()
    broken = copy.deepcopy(p5)
    del broken["phase5_output_handoff_manifest"]["pipeline_version"]
    with pytest.raises(P567RC3CompatibilityError, match="pipeline_version"):
        _adapt(p5=broken, p6=p6, p7=p7)


def test_bridge_rejects_tampered_p5_strategy_manifest() -> None:
    p5, p6, p7 = _source_inputs()
    broken = copy.deepcopy(p5)
    broken["phase6_strategy_scenario_manifest"]["handoff_mode"] = "FULL_V2"
    with pytest.raises(P567RC3CompatibilityError, match="strategy manifest artifact_sha256 mismatch"):
        _adapt(p5=broken, p6=p6, p7=p7)
