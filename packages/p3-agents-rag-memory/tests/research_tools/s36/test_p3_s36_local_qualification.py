"""Machine-readable S36 qualification checks over the real local receipt."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest


def _workspace_root() -> Path:
    return next(parent for parent in Path(__file__).resolve().parents if (parent / "data" / "raw" / "immutable").is_dir())


ROOT = _workspace_root()
EVIDENCE = ROOT / "reports" / "verification" / "p3_s36"
RECEIPT_PATH = EVIDENCE / "p3_s36_local_qualification_receipt.json"


@pytest.fixture(scope="module")
def receipt() -> dict:
    assert RECEIPT_PATH.is_file(), "run qualify_p3_s36_real.py before the evidence tests"
    return json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))


def test_s36_is_exactly_23_qualified_combinations(receipt: dict) -> None:
    assert receipt["status"] == "QUALIFIED_LOCAL"
    assert receipt["fixture_used"] is False
    assert receipt["mcp_used"] is False
    coverage = receipt["coverage"]
    assert coverage["expected_combinations"] == 23
    assert coverage["qualified_combinations"] == 23
    assert len(coverage["records"]) == 23
    assert not receipt["residual_blockers"]


def test_surface_chain_diagnostic_has_real_iv_evidence(receipt: dict) -> None:
    match = [
        item
        for item in receipt["coverage"]["records"]
        if item["operation_id"] == "get_surface_diagnostics" and item["mode_id"] == "CHAIN_DIAGNOSTIC"
    ]
    assert len(match) == 1
    item = match[0]
    assert item["status"] == "QUALIFIED_LOCAL"
    assert item["records_returned"] == 1
    assert item["evidence_count"] > 0
    assert "OBSERVED_IV_UNAVAILABLE" not in item["coverage"]["missing_dimensions"]
    decision_time = datetime.fromisoformat(receipt["decision_time"].replace("Z", "+00:00"))
    latest = datetime.fromisoformat(item["pit_proof"]["latest_available_at"].replace("Z", "+00:00"))
    assert latest <= decision_time
    assert item["pit_proof"]["input_hashes"]
    assert item["source_ids"]
    iv = receipt["materialization"]["observed_iv_coverage"]["AAPL"]
    assert iv["records"] > 0
    assert iv["latest_available_at"] <= receipt["decision_time"]


def test_spy_surface_iv_is_real_and_pit_bounded(receipt: dict) -> None:
    iv = receipt["materialization"]["observed_iv_coverage"]["SPY"]
    assert iv["records"] > 0
    assert iv["source_ids"]
    assert iv["latest_available_at"] <= receipt["decision_time"]
    surface = next(
        item
        for item in receipt["symbol_coverage"]["checks"]
        if item["symbol"] == "SPY" and item["operation_id"] == "get_surface_diagnostics"
    )
    assert surface["status"] == "QUALIFIED_LOCAL"
    assert surface["pit_proof"]["latest_available_at"] <= receipt["decision_time"]


def test_spy_is_not_counted_from_aapl_or_msft(receipt: dict) -> None:
    checks = receipt["symbol_coverage"]["checks"]
    required = {
        ("get_snapshot", "OBSERVE"),
        ("get_snapshot", "DIAGNOSTIC"),
        ("get_liquidity", "OBSERVE"),
        ("get_liquidity", "DIAGNOSTIC"),
        ("get_liquidity", "STRUCTURAL"),
        ("get_contracts", "CONTRACT_LOOKUP"),
        ("get_contracts", "CHAIN_DIAGNOSTIC"),
        ("get_chain_snapshot", "CONTRACT_LOOKUP"),
        ("get_chain_snapshot", "CHAIN_DIAGNOSTIC"),
        ("get_quote_history", "CHAIN_DIAGNOSTIC"),
        ("get_quote_history", "STRUCTURE_HISTORY"),
    }
    qualified = {
        (item["operation_id"], item["mode_id"])
        for item in checks
        if item["symbol"] == "SPY" and item["status"] == "QUALIFIED_LOCAL"
    }
    assert required <= qualified
    surface = next(item for item in checks if item["operation_id"] == "get_surface_diagnostics")
    assert surface["status"] == "QUALIFIED_LOCAL"
    assert surface["records_returned"] > 0
    assert surface["evidence_count"] > 0


def test_spy_real_nasdaq_receipts_are_hash_verified(receipt: dict) -> None:
    for filename in ("nasdaq_inside_market_capture_receipt.json", "nasdaq_options_chain_capture_receipt.json"):
        source_receipt_path = EVIDENCE / filename
        source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
        assert {item["symbol"] for item in source_receipt["captures"]} >= {"AAPL", "MSFT", "SPY"}
        assert not source_receipt.get("excluded_symbols")
        for item in source_receipt["captures"]:
            payload_path = ROOT / item["path"]
            assert hashlib.sha256(payload_path.read_bytes()).hexdigest() == item["sha256"]


def test_receipt_declares_no_fixture_or_external_mcp(receipt: dict) -> None:
    assert receipt["source"]["lse"]["capture_time"]
    assert receipt["source"]["lse"]["artifacts"]
    for filename in (
        "yahoo_corporate_actions_capture_receipt.json",
        "nasdaq_inside_market_capture_receipt.json",
        "nasdaq_options_chain_capture_receipt.json",
    ):
        source_receipt = json.loads((EVIDENCE / filename).read_text(encoding="utf-8"))
        assert source_receipt.get("fixture_used") is False
        assert source_receipt.get("mcp_used") is False
