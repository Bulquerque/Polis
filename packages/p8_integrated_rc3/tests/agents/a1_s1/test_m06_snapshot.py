from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import EvidenceResolutionStatus, StateQualityStatus
from quant_pipeline.phase_08_contracts.s1 import ResolvedCandidateEvidence, ResolvedCandidateEvidenceIndex
from quant_pipeline.phase_08_contracts.state import CurrentPortfolioAndAccountState, StateQualityReport
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import run_s1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import (
    LineageIntegrityError,
    StateInvariantError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m06_point_in_time_decision_snapshot_builder import (
    run_module,
)

from tests.agents.a1_s1.factories import P8_DECISION, full_fixture


def test_ranked_snapshot_contains_actionable_candidate_and_valid_hash() -> None:
    fixture = full_fixture(ranked=True)
    result = run_s1(fixture.request, fixture.ports)
    snapshot = result.snapshot
    assert snapshot.actionable_ranked_candidate_ids == ("cand-1",)
    assert snapshot.no_action is None
    assert snapshot.content_sha256 == canonical_sha256(
        snapshot, exclude_keys=frozenset({"content_sha256"})
    )


def test_all_abstained_produces_no_action_valid() -> None:
    fixture = full_fixture(ranked=False)
    result = run_s1(fixture.request, fixture.ports)
    assert result.snapshot.actionable_ranked_candidate_ids == ()
    assert result.snapshot.no_action is not None
    assert result.snapshot.no_action.reason.value == "NO_RANKED_CANDIDATES"


def test_blocked_state_cannot_be_sealed() -> None:
    fixture = full_fixture(ranked=True)
    result = run_s1(fixture.request, fixture.ports)
    blocked_quality = StateQualityReport(
        runtime_mode=result.m05.current_state.quality_report.runtime_mode,
        status=StateQualityStatus.BLOCKED,
        external_snapshot_present=False,
        reason_codes=("STATE_RECONCILIATION_BLOCKED",),
    )
    blocked_state = CurrentPortfolioAndAccountState(
        portfolio_state=result.m05.current_state.portfolio_state,
        account_snapshot=result.m05.current_state.account_snapshot,
        quality_report=blocked_quality,
    )
    blocked_m05 = result.m05.model_copy(update={"current_state": blocked_state})
    with pytest.raises(StateInvariantError):
        run_module(
            result.m01,
            result.m02,
            result.m03,
            result.m04,
            blocked_m05,
            market_snapshot_ref=fixture.request.market_snapshot_ref,
            store=fixture.ports.artifact_store,
            context=fixture.request.context,
        )


def test_wrong_market_snapshot_type_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    result = run_s1(fixture.request, fixture.ports)
    wrong = fixture.request.market_snapshot_ref.model_copy(update={"artifact_type": "OTHER"})
    with pytest.raises(StateInvariantError):
        run_module(
            result.m01,
            result.m02,
            result.m03,
            result.m04,
            result.m05,
            market_snapshot_ref=wrong,
            store=fixture.ports.artifact_store,
            context=fixture.request.context,
        )


def test_future_market_snapshot_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    result = run_s1(fixture.request, fixture.ports)
    future = fixture.request.market_snapshot_ref.model_copy(
        update={"available_at": P8_DECISION + timedelta(seconds=1)}
    )
    with pytest.raises(TemporalIntegrityError):
        run_module(
            result.m01,
            result.m02,
            result.m03,
            result.m04,
            result.m05,
            market_snapshot_ref=future,
            store=fixture.ports.artifact_store,
            context=fixture.request.context,
        )


def test_unresolved_ranked_candidate_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    result = run_s1(fixture.request, fixture.ports)
    unresolved = ResolvedCandidateEvidenceIndex(
        candidates=(
            ResolvedCandidateEvidence(
                candidate_id="cand-1",
                status=EvidenceResolutionStatus.UNAVAILABLE,
            ),
        ),
        full_lineage_resolution=True,
    )
    altered_m03 = result.m03.model_copy(update={"evidence_index": unresolved})
    with pytest.raises(LineageIntegrityError):
        run_module(
            result.m01,
            result.m02,
            altered_m03,
            result.m04,
            result.m05,
            market_snapshot_ref=fixture.request.market_snapshot_ref,
            store=fixture.ports.artifact_store,
            context=fixture.request.context,
        )


def test_same_inputs_produce_identical_snapshot_bytes() -> None:
    fixture_a = full_fixture(ranked=True)
    fixture_b = full_fixture(ranked=True)
    result_a = run_s1(fixture_a.request, fixture_a.ports)
    result_b = run_s1(fixture_b.request, fixture_b.ports)
    assert result_a.snapshot.model_dump_json() == result_b.snapshot.model_dump_json()
