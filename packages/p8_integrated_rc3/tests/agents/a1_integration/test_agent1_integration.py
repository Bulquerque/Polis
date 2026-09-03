from __future__ import annotations

import json
from datetime import timedelta

import pytest

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.agent1_integration.api import (
    Agent1Ports,
    Agent1RunRequest,
    run_agent1,
)
from quant_pipeline.phase_08_portfolio_control.agent1_integration.contracts import Agent1IntegrationReceiptV1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import HashMismatchError

from tests.agents.a1_integration.support.s1_factory import full_fixture


def test_ranked_candidate_runs_s1_to_s2() -> None:
    fixture = full_fixture(ranked=True)
    result = run_agent1(
        Agent1RunRequest(
            s1_request=fixture.request,
            s2_computed_at=fixture.request.context.computed_at + timedelta(seconds=1),
        ),
        Agent1Ports(s1=fixture.ports),
    )
    assert result.receipt.received_candidate_count == 1
    assert result.receipt.actionable_candidate_count == 1
    assert result.receipt.forwarded_candidate_count == 1
    assert result.receipt.no_action_valid is False
    assert result.s2.bundle.snapshot_hash == result.s1.snapshot.content_sha256
    assert result.s2.bundle.static_action_universe.forwarded_candidate_ids == ("cand-1",)


def test_all_abstained_runs_no_action_path() -> None:
    fixture = full_fixture(ranked=False)
    result = run_agent1(
        Agent1RunRequest(
            s1_request=fixture.request,
            s2_computed_at=fixture.request.context.computed_at + timedelta(seconds=1),
        ),
        Agent1Ports(s1=fixture.ports),
    )
    assert result.receipt.received_candidate_count == 1
    assert result.receipt.actionable_candidate_count == 0
    assert result.receipt.forwarded_candidate_count == 0
    assert result.receipt.no_action_valid is True
    assert result.s2.bundle.normalized_intents.candidates == ()


def test_integration_is_deterministic() -> None:
    a = full_fixture(ranked=True)
    b = full_fixture(ranked=True)
    ra = run_agent1(
        Agent1RunRequest(a.request, a.request.context.computed_at + timedelta(seconds=1)),
        Agent1Ports(s1=a.ports),
    )
    rb = run_agent1(
        Agent1RunRequest(b.request, b.request.context.computed_at + timedelta(seconds=1)),
        Agent1Ports(s1=b.ports),
    )
    assert ra.receipt == rb.receipt
    assert ra.s2.bundle == rb.s2.bundle


def test_receipt_hash_is_canonical() -> None:
    fixture = full_fixture(ranked=True)
    result = run_agent1(
        Agent1RunRequest(fixture.request, fixture.request.context.computed_at + timedelta(seconds=1)),
        Agent1Ports(s1=fixture.ports),
    )
    assert result.receipt.content_sha256 == canonical_sha256(
        result.receipt, exclude_keys=frozenset({"content_sha256"})
    )
    Agent1IntegrationReceiptV1.model_validate_json(result.receipt.model_dump_json(), strict=True)


def test_s2_time_must_follow_s1() -> None:
    fixture = full_fixture(ranked=True)
    with pytest.raises(ValueError, match="must not be before"):
        Agent1RunRequest(fixture.request, fixture.request.context.computed_at - timedelta(seconds=1))


def test_s1_failure_prevents_s2() -> None:
    fixture = full_fixture(ranked=True)
    payload = json.loads(fixture.request.p7_handoff_bytes)
    payload["content_sha256"] = "0" * 64
    bad_request = fixture.request.__class__(
        p7_handoff_bytes=json.dumps(payload).encode(),
        feedback_refs=fixture.request.feedback_refs,
        market_snapshot_ref=fixture.request.market_snapshot_ref,
        context=fixture.request.context,
    )
    with pytest.raises(HashMismatchError):
        run_agent1(
            Agent1RunRequest(bad_request, fixture.request.context.computed_at + timedelta(seconds=1)),
            Agent1Ports(s1=fixture.ports),
        )


def test_s2_time_must_be_timezone_aware() -> None:
    from datetime import datetime
    fixture = full_fixture(ranked=True)
    with pytest.raises(ValueError, match="timezone-aware"):
        Agent1RunRequest(fixture.request, datetime(2026, 8, 3, 18, 0))
