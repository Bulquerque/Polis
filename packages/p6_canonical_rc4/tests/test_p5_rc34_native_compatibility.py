from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6ContractError
from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import canonical_sha256
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import run_phase

FIXTURE = Path(__file__).parents[1] / "fixtures" / "p5_rc34_full_publication.json"
SPOTS = {"AAA": Decimal("100"), "BBB": Decimal("200"), "CCC": Decimal("50")}


def _artifact(name: str, records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "artifact_id": f"{name}-artifact",
        "content_sha256": canonical_sha256(records),
        "records": records,
    }


def _p5_bundle() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _market_inputs(decision_time: datetime) -> dict[str, object]:
    contracts: list[dict[str, object]] = []
    quotes: list[dict[str, object]] = []
    underlyings: list[dict[str, object]] = []
    expiration = decision_time + timedelta(days=1)
    for underlying_id, spot in SPOTS.items():
        underlyings.append(_underlying_record(underlying_id, spot, decision_time))
        for option_type in ("CALL", "PUT"):
            for ratio in (Decimal("0.9"), Decimal("1"), Decimal("1.1")):
                strike = spot * ratio
                contract_id = f"{underlying_id}-{option_type}-{strike}"
                contracts.append(_contract_record(contract_id, underlying_id, option_type, strike, expiration, decision_time))
                quotes.append(_quote_record(contract_id, spot, strike, decision_time))
    return {
        "clean_option_contract_panel": _artifact("contracts", contracts),
        "clean_option_quotes_panel": _artifact("quotes", quotes),
        "clean_underlying_trade_panel": _artifact("underlyings", underlyings),
    }


def _underlying_record(underlying_id: str, spot: Decimal, decision_time: datetime) -> dict[str, object]:
    return {
        "underlying_id": underlying_id,
        "quote_time": (decision_time - timedelta(minutes=1)).isoformat(),
        "available_at": (decision_time - timedelta(seconds=30)).isoformat(),
        "bid": str(spot - Decimal("0.1")),
        "ask": str(spot + Decimal("0.1")),
        "last": str(spot),
        "currency": "USD",
        "exchange": "TEST",
        "trading_status": "OPEN",
        "source_artifact_id": "underlyings-artifact",
        "source_record_id": underlying_id,
    }


def _contract_record(
    contract_id: str,
    underlying_id: str,
    option_type: str,
    strike: Decimal,
    expiration: datetime,
    decision_time: datetime,
) -> dict[str, object]:
    return {
        "contract_id": contract_id,
        "underlying_id": underlying_id,
        "option_type": option_type,
        "strike": str(strike),
        "expiration": expiration.isoformat(),
        "exercise_style": "EUROPEAN",
        "settlement_type": "CASH",
        "multiplier": "100",
        "currency": "USD",
        "listing_exchange": "TEST",
        "first_trade_date": (decision_time - timedelta(days=100)).isoformat(),
        "last_trade_date": None,
        "contract_status": "ACTIVE",
        "source_artifact_id": "contracts-artifact",
        "source_record_id": contract_id,
    }


def _quote_record(
    contract_id: str,
    spot: Decimal,
    strike: Decimal,
    decision_time: datetime,
) -> dict[str, object]:
    midpoint = max(Decimal("1"), abs(spot - strike) * Decimal("0.1") + Decimal("2"))
    return {
        "contract_id": contract_id,
        "quote_time": (decision_time - timedelta(minutes=1)).isoformat(),
        "available_at": (decision_time - timedelta(seconds=30)).isoformat(),
        "bid": str(midpoint - Decimal("0.1")),
        "ask": str(midpoint + Decimal("0.1")),
        "bid_size": "100",
        "ask_size": "100",
        "last": str(midpoint),
        "last_size": "1",
        "volume": "1000",
        "open_interest": "5000",
        "implied_volatility": "0.2",
        "quote_quality": "TWO_SIDED_EXECUTABLE",
        "source_id": f"quote-{contract_id}",
    }


def _inputs() -> tuple[dict[str, object], datetime]:
    publication = _p5_bundle()
    manifest = publication["phase6_strategy_scenario_manifest"]
    assert isinstance(manifest, dict)
    decision_time = datetime.fromisoformat(str(manifest["decision_time"]).replace("Z", "+00:00"))
    inputs = {
        "phase5_output_handoff_manifest": publication["phase5_output_handoff_manifest"],
        "phase6_strategy_scenario_manifest": manifest,
        **_market_inputs(decision_time),
    }
    return inputs, decision_time


def _configuration(decision_time: datetime, *, allow_abstained: bool) -> dict[str, object]:
    return {
        "run_id": "run-publication",
        "cycle_id": "cycle-001",
        "decision_time": decision_time.isoformat(),
        "created_at": (decision_time + timedelta(seconds=1)).isoformat(),
        "available_at": (decision_time + timedelta(seconds=1)).isoformat(),
        "seed": 7,
        "p5": {"allow_abstained_beliefs": allow_abstained},
        "strategy": {"allow_cash_secured_short_put": True},
        "risk": {"maximum_relative_spread": "1", "minimum_liquidity_score": "0"},
    }


def test_real_rc34_bundle_is_validated_and_abstention_is_fail_closed() -> None:
    inputs, decision_time = _inputs()
    result = run_phase(inputs, _configuration(decision_time, allow_abstained=False))
    outputs = result["outputs"]
    report = outputs["p5_handoff_compatibility_report"].records[0]
    beliefs = outputs["validated_market_belief_state"].records
    snapshot = outputs["strategy_market_snapshot"].records[0]

    assert report.validation_status == "COMPLETE_LEGACY_REPLAY"
    assert report.full_manifest_consumed is True
    assert len(report.receipts) == 11
    receipts = {receipt.artifact_name: receipt for receipt in report.receipts}
    assert receipts["volatility_distributions"].availability == "UNAVAILABLE"
    assert receipts["volatility_distributions"].reason_code == "P5_TARGET_UNAVAILABLE"
    assert report.artifact_usage["return_distributions"] == "SCENARIO_SOURCE_CONSUMED"
    assert report.artifact_usage["scenario_paths"] == "INTEGRITY_VALIDATED_NOT_SELECTED"
    assert len(beliefs) == 3
    assert all(len(belief.scenarios) == 101 for belief in beliefs)
    assert all(belief.scenario_source == "P5_RETURN_DISTRIBUTION" for belief in beliefs)
    assert all(belief.abstained is True for belief in beliefs)
    assert outputs["strategy_candidate_panel"].record_count == 0
    assert outputs["strategy_candidate_panel"].status.value == "EMPTY_VALID"
    assert snapshot.p5_manifest_id == report.manifest_id
    assert snapshot.p5_manifest_sha256 == report.manifest_sha256
    assert len(snapshot.p5_source_artifact_ids) == 11
    assert len(snapshot.p5_source_hashes) == 11


def test_explicit_research_override_generates_horizon_aligned_candidates_deterministically() -> None:
    inputs, decision_time = _inputs()
    configuration = _configuration(decision_time, allow_abstained=True)
    first = run_phase(inputs, configuration)["outputs"]["strategy_candidate_panel"]
    second = run_phase(inputs, configuration)["outputs"]["strategy_candidate_panel"]

    assert first.record_count > 0
    assert {candidate.horizon_days for candidate in first.records} == {1}
    assert tuple(candidate.candidate_id for candidate in first.records) == tuple(
        candidate.candidate_id for candidate in second.records
    )


def test_rc34_manifest_hash_tampering_is_rejected() -> None:
    inputs, decision_time = _inputs()
    tampered = deepcopy(inputs)
    manifest = tampered["phase6_strategy_scenario_manifest"]
    assert isinstance(manifest, dict)
    reference = manifest["market_belief_state"]
    assert isinstance(reference, dict)
    reference["content_hash"] = "0" * 64

    with pytest.raises(Phase6ContractError) as captured:
        run_phase(tampered, _configuration(decision_time, allow_abstained=False))

    assert captured.value.reason_code == "P6_P5_MANIFEST_INVALID"


def test_rc34_embedded_artifact_tampering_is_rejected() -> None:
    inputs, decision_time = _inputs()
    tampered = deepcopy(inputs)
    handoff = tampered["phase5_output_handoff_manifest"]
    assert isinstance(handoff, dict)
    embedded = handoff["embedded_v2_artifacts"]
    assert isinstance(embedded, dict)
    belief_artifact = embedded["market_belief_state"]
    assert isinstance(belief_artifact, dict)
    records = belief_artifact["records"]
    assert isinstance(records, list)
    first = records[0]
    assert isinstance(first, dict)
    first["confidence"] = "0.1"

    with pytest.raises(Phase6ContractError) as captured:
        run_phase(tampered, _configuration(decision_time, allow_abstained=False))

    assert captured.value.reason_code == "P6_MANIFEST_REFERENCE_INVALID"


def test_foreign_p5_run_or_cycle_is_rejected_by_canonical_p6_runtime() -> None:
    inputs, decision_time = _inputs()
    bad = _configuration(decision_time, allow_abstained=False)
    bad["run_id"] = "foreign-run"
    with pytest.raises(Phase6ContractError) as captured:
        run_phase(inputs, bad)
    assert captured.value.reason_code == "P6_MARKET_CLOCK_MISMATCH"

    bad = _configuration(decision_time, allow_abstained=False)
    bad["cycle_id"] = "foreign-cycle"
    with pytest.raises(Phase6ContractError) as captured:
        run_phase(inputs, bad)
    assert captured.value.reason_code == "P6_MARKET_CLOCK_MISMATCH"
