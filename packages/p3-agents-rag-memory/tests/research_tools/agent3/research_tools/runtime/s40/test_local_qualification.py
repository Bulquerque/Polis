from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[8]
sys.path.insert(0, str(WORKSPACE / "tools" / "p3_s40"))

import qualify_local as s40
from qualify_local import run_qualification


def test_all_eight_s40_contracts_have_hard_receipts() -> None:
    result = asyncio.run(run_qualification())
    receipts = result["module_receipts"]
    assert tuple(receipts) == tuple(f"P3.S40.M0{index}" for index in range(1, 9))
    for module_id, receipt in receipts.items():
        assert receipt["status"] == "QUALIFIED_LOCAL", module_id
        assert receipt["qualification_scope"] == "S40_CONTRACT_ONLY_LOCAL"
        assert receipt["production_data_qualification"] is False
        assert receipt["fixture_presented_as_qualification"] is False
        assert len(receipt["contract_sha256"]) == 64
        assert len(receipt["implementation_sha256"]) == 64
        assert receipt["input_hashes"]
        assert receipt["output_hashes"]
        assert receipt["lineage"]["producer_module_id"] == module_id
        assert all(value == "PASS" for value in receipt["tests"].values())
        assert receipt["negative_checks"]
        assert all(value == "PASS" for value in receipt["negative_checks"].values())
        assert len(receipt["receipt_hash"]) == 64
    assert result["real_p3_bundle_sha256"]
    assert all(value == "PASS" for value in result["negative_checks"].values())
    assert result["release_gate_status"] == "PASS"
    assert result["qualification_status"] == "QUALIFIED_LOCAL"
    assert result["capability_100_percent"] is True
    assert result["release_gate_counts"] == {
        "blocked_operations": 0,
        "degraded_operations": 0,
        "failed_operations": 0,
        "qualified_operations": 103,
    }
    assert result["residual_blockers"] == []
    assert result["fixture_used"] is False
    assert result["mcp_used"] is False
    assert result["production_promotion_allowed"] is False
    assert result["upstream_evidence"]["S35"]["qualified_modes"] == 18
    assert result["upstream_evidence"]["S36"]["qualified_modes"] == 23


def test_missing_s35_receipt_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(s40, "S35_RECEIPT", tmp_path / "missing-s35.json")
    with pytest.raises(RuntimeError, match="missing"):
        s40._real_upstream_evidence()


def test_altered_s35_receipt_fails_closed(tmp_path, monkeypatch) -> None:
    source = s40.S35_RECEIPT
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["fixture_used"] = True
    altered = tmp_path / "altered-s35.json"
    altered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(s40, "S35_RECEIPT", altered)
    with pytest.raises(RuntimeError, match="fixture or MCP"):
        s40._real_upstream_evidence()


def test_missing_s36_combination_fails_closed(tmp_path, monkeypatch) -> None:
    source = s40.S36_RECEIPT
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["coverage"]["records"] = payload["coverage"]["records"][:-1]
    body = {key: value for key, value in payload.items() if key not in {"content_hash", "receipt_hash"}}
    payload["receipt_hash"] = s40.content_hash(body)
    altered = tmp_path / "missing-s36-combination.json"
    altered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(s40, "S36_RECEIPT", altered)
    with pytest.raises(RuntimeError, match="coverage count|coverage is incomplete"):
        s40._real_upstream_evidence()


def test_receipt_is_replay_stable() -> None:
    first = asyncio.run(run_qualification())
    second = asyncio.run(run_qualification())
    assert first["release_gate_hash"] == second["release_gate_hash"]
    assert first["module_receipts"] == second["module_receipts"]


def test_canonical_report_has_no_fake_production_claim() -> None:
    report = Path("reports/verification/p3_s40_local_qualification/p3_s40_local_qualification_receipt.json")
    if report.exists():
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["production_data_qualification"] is False
        assert payload["fixture_presented_as_qualification"] is False
