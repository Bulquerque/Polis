from __future__ import annotations

import copy
import pytest

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M01_phase_feedback_router import run_module as route_feedback
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M02_blocking_issue_dispatcher import run_module as route_blockers
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M03_nonblocking_warning_dispatcher import run_module as route_advisories
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M04_zero_trust_feedback_manifest_builder import run_module as build_manifest

SOURCES = ["release_gate_report", "phase_health_panel", "code_quality_report", "global_test_report"]


def _lineage(char: str) -> str:
    return "sha256:" + char * 64


def _base_sources(phase_count: int = 3) -> dict:
    phases = [{"phase_id": f"P{i}", "status": "PASS", "findings": []} for i in range(phase_count)]
    result = {}
    for index, name in enumerate(SOURCES):
        result[name] = {
            "artifact_id": name,
            "lineage_id": _lineage(str(index + 1)),
            "phases": copy.deepcopy(phases),
        }
    return result


def test_dynamic_phase_registry_is_not_hardcoded_to_ten():
    panel = route_feedback(_base_sources(3), {"created_at": "2026-07-22T00:00:00Z"})["outputs"]["phase_zero_trust_feedback_panel"]
    assert panel["phase_count"] == 3
    assert [p["phase_id"] for p in panel["phases"]] == ["P0", "P1", "P2"]


def test_identical_findings_from_multiple_sources_are_deduplicated():
    value = _base_sources()
    finding = {
        "finding_id": "HASH-1",
        "reason_code": "HASH_MISMATCH",
        "severity": "CRITICAL",
        "condition_type": "INTEGRITY_FAILURE",
        "readiness_impact": "BLOCKS_READINESS",
        "release_impact": "BLOCKS_RELEASE",
        "message": "hash mismatch",
        "owner": "P0",
        "action": "restore canonical artifact",
    }
    value["release_gate_report"]["phases"][0]["findings"] = [copy.deepcopy(finding)]
    value["code_quality_report"]["phases"][0]["findings"] = [copy.deepcopy(finding)]
    panel = route_feedback(value)["outputs"]["phase_zero_trust_feedback_panel"]
    assert panel["finding_count"] == 1
    assert panel["deduplicated_source_finding_count"] == 1
    assert len(panel["findings"][0]["source_evidence"]) == 2


def test_same_finding_id_with_conflicting_semantics_fails_closed():
    value = _base_sources()
    first = {"finding_id": "X", "severity": "WARNING", "message": "a", "owner": "P0", "action": "review"}
    second = {"finding_id": "X", "severity": "WARNING", "message": "different", "owner": "P0", "action": "review"}
    value["release_gate_report"]["phases"][0]["findings"] = [first]
    value["code_quality_report"]["phases"][0]["findings"] = [second]
    with pytest.raises(ContractValidationError):
        route_feedback(value)


def test_not_started_is_notice_but_blocks_readiness_without_being_critical():
    value = _base_sources()
    value["phase_health_panel"]["phases"][1].update(
        {
            "development_status": "NOT_STARTED",
            "test_status": "NOT_RUN",
            "health_status": "UNKNOWN",
            "qualification_status": "NOT_ELIGIBLE",
            "readiness": "NOT_READY",
        }
    )
    panel = route_feedback(value)["outputs"]["phase_zero_trust_feedback_panel"]
    phase = next(p for p in panel["phases"] if p["phase_id"] == "P1")
    assert phase["status"] == "BLOCKED"
    finding = next(f for f in phase["findings"] if f["reason_code"] == "DEVELOPMENT_NOT_STARTED")
    assert finding["severity"] == "NOTICE"
    assert finding["readiness_blocking"] is True
    assert panel["critical_count"] == 0


def test_warning_cannot_be_release_blocking():
    value = _base_sources()
    value["release_gate_report"]["phases"][0]["findings"] = [
        {
            "finding_id": "W-BLOCK",
            "severity": "WARNING",
            "message": "warning",
            "owner": "P0",
            "release_blocking": True,
            "action": "review",
        }
    ]
    with pytest.raises(ContractValidationError):
        route_feedback(value)


def test_manifest_exactly_partitions_blocking_and_nonblocking_findings():
    value = _base_sources()
    value["release_gate_report"]["phases"][0]["findings"] = [
        {"finding_id": "B", "severity": "BLOCKING", "message": "broken", "owner": "P0", "action": "fix"}
    ]
    value["code_quality_report"]["phases"][1]["findings"] = [
        {"finding_id": "W", "severity": "WARNING", "message": "watch", "owner": "P1", "action": "review"}
    ]
    panel = route_feedback(value)["outputs"]["phase_zero_trust_feedback_panel"]
    blocking = route_blockers({"phase_zero_trust_feedback_panel": panel})["outputs"]["blocking_issue_report"]
    advisory = route_advisories({"phase_zero_trust_feedback_panel": panel})["outputs"]["nonblocking_warning_report"]
    manifest = build_manifest(
        {
            "phase_zero_trust_feedback_panel": panel,
            "blocking_issue_report": blocking,
            "nonblocking_warning_report": advisory,
        }
    )["outputs"]["zero_trust_feedback_manifest"]
    assert manifest["exact_finding_coverage"] is True
    assert manifest["finding_count"] == panel["finding_count"]
    assert len(manifest["phase_feedback_packets"]) == panel["phase_count"]
    assert blocking["issues"][0]["routing_status"] == "ROUTED_TO_OWNER"
    assert blocking["external_dispatch_performed"] is False
