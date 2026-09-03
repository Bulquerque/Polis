from __future__ import annotations

from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.qualification.release import build_release_gate
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.models import (
    ConsumerCompatibilityStatus,
    HandlerRegistryCompletenessReport,
    OperationModeQualificationMatrix,
    OperationModeQualificationRecord,
    QualificationStatus,
    RegistryStatus,
    ResearchToolLeakageReport,
    S21RuntimePreflightReport,
    S40Lineage,
)
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash


def lineage(module: str) -> S40Lineage:
    return S40Lineage(lineage_id=f"{module}:lineage", producer_module_id=module)


def test_release_gate_is_degraded_until_p4_and_p9_are_wired():
    l = lineage("P3.S40.M08")
    completeness_payload = {
        "status": RegistryStatus.READY,
        "expected_operations": 1,
        "registered_operations": 1,
        "executable_operations": 1,
        "lineage": l,
    }
    completeness = HandlerRegistryCompletenessReport(
        **completeness_payload,
        report_hash=content_hash(completeness_payload),
    )
    preflight_payload = {
        "status": RegistryStatus.READY,
        "operation_count": 1,
        "entitlement_operation_count": 1,
        "lineage": l,
    }
    preflight = S21RuntimePreflightReport(
        **preflight_payload,
        report_hash=content_hash(preflight_payload),
    )
    record = OperationModeQualificationRecord(
        tool_id="test.echo.v1",
        operation_id="echo",
        mode_id="BASIC",
        status=QualificationStatus.QUALIFIED_LOCAL,
        handler_id="test.echo.handler.v1",
        contract_tests_passed=1,
        integration_tests_passed=1,
        leakage_tests_passed=1,
        replay_tests_passed=1,
    )
    matrix_payload = {"records": (record,), "lineage": l}
    matrix = OperationModeQualificationMatrix(
        **matrix_payload,
        matrix_hash=content_hash(matrix_payload),
    )
    leakage_payload = {
        "status": RegistryStatus.READY,
        "tests_run": 1,
        "tests_passed": 1,
        "invariants": ("pit",),
        "lineage": l,
    }
    leakage = ResearchToolLeakageReport(
        **leakage_payload,
        report_hash=content_hash(leakage_payload),
    )
    downstream = {"status": ConsumerCompatibilityStatus.PRODUCER_READY_CONSUMER_NOT_YET_WIRED.value}
    gate, issues = build_release_gate(
        completeness=completeness,
        preflight=preflight,
        qualification=matrix,
        leakage=leakage,
        p4_report=downstream,
        p9_report=downstream,
        contract_report={"status": "PASS"},
        schema_report={"status": "PASS"},
        code_quality_report={"status": "PASS"},
        hash_integrity_report={"status": "PASS"},
        rollback_report={"status": "PASS"},
        lineage=l,
    )
    assert gate.status.value == "DEGRADED"
    assert not issues.records
    assert gate.p5_direct_connection_absent is True
