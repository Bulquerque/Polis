from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quant_pipeline.phase_03_agents_rag_memory.contracts import content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import (
    CompanyOperationModeQualification,
    CompanyOperationReadinessPanel,
    CompanyToolBundle,
    HandlerBundleManifest,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[5]
RECEIPT = PACKAGE_ROOT / "reports" / "verification" / "p3_s38_local_qualification.json"
AUDIT = PACKAGE_ROOT / "reports" / "verification" / "p3_s38_closure_audit.json"


def load_receipt() -> dict:
    assert RECEIPT.is_file(), f"missing canonical S38 receipt: {RECEIPT}"
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_s38_receipt_is_hashed_and_real_local_only():
    receipt = load_receipt()
    declared = receipt.pop("content_hash")
    assert content_hash(receipt) == declared
    assert receipt["qualification_status"] == "QUALIFIED_LOCAL"
    assert receipt["fixture_used"] is False
    assert receipt["source_scope"] == "REAL_PUBLIC_SEC_API_LOCAL_MATERIALIZED"
    assert receipt["mcp_used"] is False
    assert receipt["closure_layers"]["capability_layer"]["capability_100_percent"] is True
    assert receipt["closure_layers"]["capability_layer"]["blocked_capabilities"] == 0
    assert receipt["residual_blockers"] == []
    for path_text, expected_hash in receipt["source_hashes"].items():
        path = Path(path_text)
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    for paths in receipt["evidence_paths"].values():
        assert all(Path(path).is_file() for path in paths)


def test_s38_hard_audit_closes_contract_and_capability_layers():
    assert AUDIT.is_file(), f"missing hard S38 audit: {AUDIT}"
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    declared = audit.pop("content_hash")
    assert content_hash(audit) == declared
    assert audit["phase_audit"]["status"] == "passed"
    totals = audit["phase_audit"]["totals"]
    assert totals["contract_requirements_passed"] == 6
    assert totals["capability_requirements_passed"] == 7
    assert totals["capability_requirements_blocked"] == 0
    assert audit["closure_layers"]["contract_layer"]["status"] == "QUALIFIED_LOCAL"
    assert audit["closure_layers"]["capability_layer"]["status"] == "QUALIFIED_LOCAL"
    assert audit["closure_layers"]["capability_layer"]["capability_100_percent"] is True


def test_s38_receipt_has_six_direct_module_proofs_and_negative_tests():
    receipt = load_receipt()
    modules = {item["module_id"]: item for item in receipt["modules"]}
    assert set(modules) == {f"P3.S38.M0{index}" for index in range(1, 7)}
    assert all(item["status"] == "QUALIFIED_LOCAL" for item in modules.values())
    assert receipt["tests"]["contract_negative_tests"] == 32
    assert receipt["tests"]["leakage_negative_tests"] == 6
    assert receipt["tests"]["future_record_rejection"] == "PASS"
    assert receipt["tests"]["missing_availability_rejection"] == "PASS"
    assert receipt["tests"]["deterministic_replay"] == "PASS"
    assert receipt["tests"]["real_xbrl_facts"] == "PASS"
    assert receipt["tests"]["real_statements"] == "PASS"
    assert receipt["tests"]["real_capital_actions"] == "PASS"
    assert receipt["tests"]["malformed_sec_input"] == "PASS"
    assert receipt["tests"]["altered_content_rejection"] == "PASS"
    assert all(value == "QUALIFIED_LOCAL" for value in receipt["operational_capabilities"].values())
    assert receipt["source_artifacts"]


def test_s38_module_outputs_validate_against_local_contract_models():
    outputs = load_receipt()["module_outputs"]
    CompanyOperationReadinessPanel.model_validate(outputs["M01"]["company_operation_readiness_panel"], strict=False)
    HandlerBundleManifest.model_validate(outputs["M02"]["company_profile_filing_handler_bundle"], strict=False)
    HandlerBundleManifest.model_validate(outputs["M03"]["financial_statement_handler_bundle"], strict=False)
    HandlerBundleManifest.model_validate(outputs["M04"]["earnings_quality_capital_allocation_handler_bundle"], strict=False)
    HandlerBundleManifest.model_validate(outputs["M05"]["guidance_peers_valuation_handler_bundle"], strict=False)
    CompanyToolBundle.model_validate(outputs["M06"]["company_tool_handler_bundle"], strict=False)
    CompanyOperationModeQualification.model_validate(outputs["M06"]["company_operation_mode_qualification"], strict=False)


def test_s38_capability_statuses_are_qualified_and_empty_views_are_explicit():
    records = load_receipt()["module_outputs"]["M06"]["company_operation_mode_qualification"]["records"]
    assert {record["status"] for record in records} == {"QUALIFIED_LOCAL"}
    profile_statuses = {record["status"] for record in records if record["operation_id"] == "get_profile"}
    assert profile_statuses == {"QUALIFIED_LOCAL"}


def test_s38_real_views_are_not_the_legacy_p1_blobs():
    receipt = load_receipt()
    assert all("p1_artifacts\\sec" not in path for path in receipt["source_artifacts"])
    assert receipt["view_manifest"]["views"]
    views = {item["view_id"]: item for item in receipt["view_manifest"]["views"]}
    assert views["financial_statements"]["row_count"] > 0
    assert views["corporate_actions"]["row_count"] > 0
    assert views["company_guidance"]["row_count"] >= 0
    assert views["company_peers"]["empty_valid"] is True
