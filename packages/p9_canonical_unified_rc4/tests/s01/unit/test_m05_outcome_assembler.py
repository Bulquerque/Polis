from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_pipeline.phase_09.contracts.base import EvidenceClass
from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256, sha256_bytes
from quant_pipeline.phase_09.contracts.maturity import (
    LifecycleStatus,
    MaturityDecision,
    MaturityState,
    MaturitySubject,
    MaturitySubjectManifest,
    MaturitySubjectManifestPayload,
    OutcomeMaturityPanel,
)
from quant_pipeline.phase_09.contracts.outcomes import MarkSource, MarkingPolicy, MarketMark
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m05_outcome_assembler import (
    RealizedOutcomeAndMarkQualityAssembler,
)


def _subject_manifest(t0):
    payload = MaturitySubjectManifestPayload(
        manifest_id="m",
        subjects=(
            MaturitySubject(
                subject_id="s",
                target_type="PRIMARY",
                instrument_id="i",
                contract_key="c",
                decision_time=t0,
                horizon_end=t0 + timedelta(days=1),
                data_available_at=t0 + timedelta(days=1),
                lifecycle_status=LifecycleStatus.CLOSED,
                reference_price=Decimal("100"),
                quantity=Decimal("2"),
                contract_multiplier=Decimal("1"),
            ),
        ),
    )
    return MaturitySubjectManifest(
        payload=payload,
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
    )


def _maturity(t0):
    return OutcomeMaturityPanel(
        decisions=(
            MaturityDecision(
                subject_id="s",
                metric_family="primary",
                state=MaturityState.MATURED,
                required_at=t0 + timedelta(days=1),
                evaluation_as_of=t0 + timedelta(days=2),
                observable=True,
                eligible=True,
            ),
        )
    )


def test_bid_ask_midpoint_builds_observable_counterfactual() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mark = MarketMark(
        mark_id="mark",
        subject_id="s",
        instrument_id="i",
        contract_key="c",
        observed_at=t0 + timedelta(days=1),
        available_at=t0 + timedelta(days=1),
        source=MarkSource.BID_ASK,
        bid=Decimal("109"),
        ask=Decimal("111"),
        source_sha256=sha256_bytes(b"mark"),
    )
    panel, counterfactuals, _, _ = RealizedOutcomeAndMarkQualityAssembler().assemble(
        subjects=_subject_manifest(t0),
        maturity_panel=_maturity(t0),
        executed_outcomes=(),
        market_marks=(mark,),
        policy=MarkingPolicy(policy_id="p", max_staleness_seconds=200_000),
        evaluation_as_of=t0 + timedelta(days=2),
    )
    record = panel.records[0]
    assert record.evidence_class is EvidenceClass.OBSERVABLE_COUNTERFACTUAL
    assert record.mark_price == Decimal("110")
    assert record.outcome_value == Decimal("20")
    assert counterfactuals.records == (record,)


def test_stale_mark_does_not_become_zero() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mark = MarketMark(
        mark_id="old",
        subject_id="s",
        instrument_id="i",
        contract_key="c",
        observed_at=t0,
        available_at=t0,
        source=MarkSource.LAST,
        last=Decimal("101"),
        source_sha256=sha256_bytes(b"old"),
    )
    panel, _, report, _ = RealizedOutcomeAndMarkQualityAssembler().assemble(
        subjects=_subject_manifest(t0),
        maturity_panel=_maturity(t0),
        executed_outcomes=(),
        market_marks=(mark,),
        policy=MarkingPolicy(policy_id="p", max_staleness_seconds=60),
        evaluation_as_of=t0 + timedelta(days=2),
    )
    record = panel.records[0]
    assert record.evidence_class is EvidenceClass.UNAVAILABLE
    assert record.outcome_value is None
    assert report.stale_count == 1


def test_model_mark_requires_explicit_capability() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mark = MarketMark(
        mark_id="model",
        subject_id="s",
        instrument_id="i",
        contract_key="c",
        observed_at=t0 + timedelta(days=1),
        available_at=t0 + timedelta(days=1),
        source=MarkSource.MODEL,
        model_price=Decimal("105"),
        source_sha256=sha256_bytes(b"model"),
    )
    panel, _, _, _ = RealizedOutcomeAndMarkQualityAssembler().assemble(
        subjects=_subject_manifest(t0),
        maturity_panel=_maturity(t0),
        executed_outcomes=(),
        market_marks=(mark,),
        policy=MarkingPolicy(
            policy_id="p",
            max_staleness_seconds=200_000,
            allow_model_marks=True,
        ),
        evaluation_as_of=t0 + timedelta(days=2),
    )
    assert panel.records[0].evidence_class is EvidenceClass.MODEL_BASED_COUNTERFACTUAL
    assert "MODEL_BASED" in panel.records[0].quality_flags
