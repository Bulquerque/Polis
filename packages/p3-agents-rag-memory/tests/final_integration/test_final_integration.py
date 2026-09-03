from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_pipeline.phase_03_agents_rag_memory.final_integration.gates import (
    FinalIntegrationGateEngine,
)
from quant_pipeline.phase_03_agents_rag_memory.final_integration.models import GateStatus
from quant_pipeline.phase_03_agents_rag_memory.final_integration.templates import (
    write_templates,
)
from phase_03_extracted.phase_03_agents_rag_memory_agent_package_RC4_1.tests.final_integration.evidence_factory import (
    KEYRING,
    RELEASE_ID,
    RELEASE_SHA256,
    add_candidate_and_p0,
    build_valid_evidence,
    seal,
    write,
)


def engine() -> FinalIntegrationGateEngine:
    return FinalIntegrationGateEngine(
        release_id=RELEASE_ID,
        release_sha256=RELEASE_SHA256,
        keyring=KEYRING,
    )


def test_templates_fail_closed(tmp_path: Path) -> None:
    write_templates(tmp_path)
    assert engine().evaluate(tmp_path).overall_status is GateStatus.NOT_STARTED


def test_full_chain_requires_external_p0_then_passes(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    gate_engine = engine()
    before = gate_engine.evaluate(tmp_path)
    assert [gate.status for gate in before.gates[:7]] == [GateStatus.PASS] * 7
    assert before.gates[-1].status is GateStatus.FAIL
    add_candidate_and_p0(tmp_path, gate_engine)
    after = gate_engine.evaluate(tmp_path)
    assert after.overall_status is GateStatus.PASS
    assert after.production_promotion_allowed


def test_dataset_without_pit_fails_data_gate(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    path = tmp_path / "evaluation_dataset_manifest.json"
    payload = json.loads(path.read_text())
    payload["point_in_time_complete"] = False
    seal(payload, "dataset_hash")
    write(path, payload)
    report = engine().evaluate(tmp_path)
    assert report.gates[-1].gate_id == "P3.DATA"
    assert report.gates[-1].status is GateStatus.FAIL


def test_variant_output_hash_mismatch_fails_experiment_gate(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    path = tmp_path / "evaluation_observation_panel.json"
    payload = json.loads(path.read_text())
    payload["observations"][0]["output_artifact_hash"] = "f" * 64
    seal(payload, "panel_hash")
    write(path, payload)
    report = engine().evaluate(tmp_path)
    assert report.gates[-1].gate_id == "P3.EXPERIMENT"
    assert report.gates[-1].status is GateStatus.FAIL


def test_receipt_from_wrong_authority_fails_cross_phase_gate(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    path = tmp_path / "cross_phase_receipts.json"
    payload = json.loads(path.read_text())
    payload["receipts"][0]["authority"] = "P3_RUNTIME"
    seal(payload, "bundle_hash")
    write(path, payload)
    report = engine().evaluate(tmp_path)
    assert report.gates[-1].gate_id == "P3.CROSS_PHASE"
    assert report.gates[-1].status is GateStatus.FAIL


def test_qualification_log_hash_mismatch_fails_quality_gate(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    (tmp_path / "qualification/module_regression.txt").write_text("tampered")
    report = engine().evaluate(tmp_path)
    assert report.gates[-1].gate_id == "P3.QUALITY"
    assert report.gates[-1].status is GateStatus.FAIL


def test_candidate_is_invalid_after_evidence_changes(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    gate_engine = engine()
    add_candidate_and_p0(tmp_path, gate_engine)
    assert gate_engine.evaluate(tmp_path).overall_status is GateStatus.PASS
    path = tmp_path / "population_calibration_bundle.json"
    payload = json.loads(path.read_text())
    payload["version_stability_score"] = 0.96
    seal(payload, "bundle_hash")
    write(path, payload)
    report = gate_engine.evaluate(tmp_path)
    assert report.overall_status is GateStatus.FAIL


def test_release_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    build_valid_evidence(tmp_path)
    wrong = FinalIntegrationGateEngine(
        release_id=RELEASE_ID,
        release_sha256="f" * 64,
        keyring=KEYRING,
    )
    assert wrong.evaluate(tmp_path).overall_status is GateStatus.NOT_STARTED


def test_p3_cannot_build_candidate_before_quality_passes(tmp_path: Path) -> None:
    write_templates(tmp_path)
    gate_engine = engine()
    with pytest.raises(ValueError):
        gate_engine.build_candidate(tmp_path, gate_engine.evaluate(tmp_path))
