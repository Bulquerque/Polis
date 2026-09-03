from __future__ import annotations

import json
from copy import deepcopy

import pytest

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.p7 import P7RankingHandoffV1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import (
    CandidateConservationError,
    ContractIntegrityError,
    HashMismatchError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m01_phase7_handoff_contract_validator import (
    run_module,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import ContractCompatibilityPolicy

from tests.agents.a1_s1.factories import P8_DECISION, context, full_fixture


def _object(raw: bytes) -> dict[str, object]:
    return json.loads(raw)


def _bytes(payload: dict[str, object], *, rehash: bool = True) -> bytes:
    if rehash:
        payload["content_sha256"] = "0" * 64
        provisional_raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        model = P7RankingHandoffV1.model_validate_json(provisional_raw, strict=True)
        payload["content_sha256"] = canonical_sha256(
            model, exclude_keys=frozenset({"content_sha256"})
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def test_valid_handoff_is_accepted() -> None:
    fixture = full_fixture(ranked=True)
    result = run_module(
        fixture.request.p7_handoff_bytes,
        context=fixture.request.context,
        policy=ContractCompatibilityPolicy(),
    )
    assert result.bundle.handoff.ranked[0].candidate_id == "cand-1"
    assert result.bundle.compatibility.contract_mode == "FULL_NATIVE"


def test_nested_forbidden_field_is_rejected_before_schema_coercion() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["ranked"][0]["metadata"] = {"portfolio_weight": 0.5}  # type: ignore[index]
    with pytest.raises(ContractIntegrityError, match="forbidden fields"):
        run_module(_bytes(payload, rehash=False), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_tampered_embedded_hash_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["producer_release"] = "tampered"
    with pytest.raises(HashMismatchError):
        run_module(_bytes(payload, rehash=False), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_handoff_unavailable_at_p8_decision_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["available_at"] = "2026-08-03T18:01:00Z"
    with pytest.raises(TemporalIntegrityError):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_candidate_in_two_terminal_populations_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["abstained"] = [
        {
            "candidate_id": "cand-1",
            "terminal_state": "ABSTAINED",
            "reason_codes": ["LOW_CONFIDENCE"],
            "missing_evidence_refs": [],
            "p6_economic_package_ref": None,
        }
    ]
    with pytest.raises(CandidateConservationError):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_duplicate_inside_ranked_population_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    duplicate = deepcopy(payload["ranked"][0])  # type: ignore[index]
    duplicate["rank"] = 2
    payload["ranked"].append(duplicate)  # type: ignore[union-attr]
    payload["comparison_groups"][0]["member_candidate_ids"] = ["cand-1"]  # type: ignore[index]
    with pytest.raises(CandidateConservationError, match="duplicate"):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_received_ids_must_equal_terminal_population() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["received_candidate_ids"] = ["cand-1", "ghost"]
    with pytest.raises(CandidateConservationError):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_unknown_comparison_group_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["ranked"][0]["comparison_group_id"] = "missing"  # type: ignore[index]
    with pytest.raises(ContractIntegrityError, match="unknown comparison group"):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_non_contiguous_ranks_are_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["ranked"][0]["rank"] = 2  # type: ignore[index]
    with pytest.raises(ContractIntegrityError, match="contiguous"):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_ordinal_score_cannot_carry_cardinal_value() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["ranked"][0]["score_value"] = 1.25  # type: ignore[index]
    with pytest.raises(ContractIntegrityError, match="ORDINAL"):
        run_module(_bytes(payload, rehash=False), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_extra_field_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["unexpected"] = "not allowed"
    with pytest.raises(ContractIntegrityError, match="Extra inputs"):
        run_module(_bytes(payload, rehash=False), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_naive_datetime_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["decision_time"] = P8_DECISION.replace(tzinfo=None).isoformat()
    with pytest.raises(ContractIntegrityError, match="timezone-aware"):
        run_module(_bytes(payload, rehash=False), context=context(), policy=ContractCompatibilityPolicy())


def test_foreign_run_or_cycle_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    for field, value in (("run_id", "foreign-run"), ("cycle_id", "foreign-cycle")):
        payload = _object(fixture.request.p7_handoff_bytes)
        payload[field] = value
        with pytest.raises(TemporalIntegrityError, match="run/cycle"):
            run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())


def test_foreign_decision_clock_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    payload = _object(fixture.request.p7_handoff_bytes)
    payload["decision_time"] = "2026-08-03T18:01:00Z"
    payload["computed_at"] = "2026-08-03T18:01:00Z"
    payload["recorded_at"] = "2026-08-03T18:01:00Z"
    payload["available_at"] = "2026-08-03T18:01:00Z"
    with pytest.raises(TemporalIntegrityError, match="decision_time"):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())

    payload = _object(fixture.request.p7_handoff_bytes)
    payload["market_cutoff_at"] = "2026-08-03T17:54:00Z"
    with pytest.raises(TemporalIntegrityError, match="market_cutoff_at"):
        run_module(_bytes(payload), context=fixture.request.context, policy=ContractCompatibilityPolicy())
