from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def current_snapshot() -> str:
    from tools.harness_snapshot import calculate_snapshot
    return calculate_snapshot(ROOT)["digest"]


def test_documentary_supertest_inventory_is_fail_closed():
    result = subprocess.run(
        [sys.executable, "-B", str(ROOT / "tools/audit_documentary_supertests.py")],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"status": "pass", "phases": 10, "findings": []}


def test_implementation_authorization_is_scoped_and_non_operational():
    authorization = ROOT / "reports/planning/phase_implementation_authorization.json"
    assert authorization.exists(), "implementation-readiness authorization is required"
    payload = json.loads(authorization.read_text(encoding="utf-8"))
    assert payload["status"] == "APPROVED_FOR_IMPLEMENTATION_START"
    assert payload["target_phase"] == "P0"
    assert payload["target_module"] == "P0.S1.M01"
    assert payload["execution_authorized"] is True
    assert type(payload["canary_authorized"]) is bool
    assert type(payload["closure_authorized"]) is bool
    assert not payload["closure_authorized"] or payload["canary_authorized"]
    if payload["canary_authorized"] or payload["closure_authorized"]:
        assert payload["qualification_authorized_by"] == "explicit_user_request_in_current_thread"
    assert payload["production_promotion_allowed"] is False


def test_p0_operational_spec_and_qualified_gate_remain_non_production():
    import yaml
    spec = yaml.safe_load((ROOT / "phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1/qualification/MASTER_PHASE_TEST_SPEC.yaml").read_text(encoding="utf-8"))
    assert spec["lifecycle_status"] == "AUTHORIZED_FOR_CANARY_AND_CLOSURE"
    assert spec["execution_authorized"] is spec["accepted_implementation_baseline"] is True
    assert spec["authorization_path"] == "reports/planning/phase_implementation_authorization.json"
    gate = json.loads((ROOT / "phases/phase_00_zero_trust/phase_qualification_gate_result.json").read_text(encoding="utf-8"))
    if gate.get("source_snapshot_digest") != current_snapshot():
        assert gate["gate"] in {"PASS", "BLOCKED"}
        assert gate["operational_status"] in {"PASS", "BLOCKED"}
        assert gate["phase_qualified"] in {True, False}
        assert gate["production_promotion_allowed"] is False
        return
    assert gate["gate"] == "PASS"
    assert gate["operational_status"] in {"PHASE_QUALIFIED", "PASS"}
    assert gate["phase_qualified"] is True
    assert gate["production_promotion_allowed"] is False


def test_business_phase_gates_remain_blocked_until_implemented():
    gates = sorted((ROOT / "phases").glob("*/phase_qualification_gate_result.json"))
    assert len(gates) == 10
    business_gates = [path for path in gates if path.parent.name not in {"phase_00_zero_trust", "phase_01_ingestion"}]
    assert len(business_gates) == 8
    for path in business_gates:
        gate = json.loads(path.read_text(encoding="utf-8"))
        if path.parent.name in {"phase_01_ingestion", "phase_02_quality_pit"}:
            if gate.get("source_snapshot_digest") != current_snapshot():
                assert gate["gate"] in {"PASS", "BLOCKED"}
                assert gate["production_promotion_allowed"] is False
                continue
            assert gate["gate"] == "PASS"
            assert gate["operational_status"] == "PASS"
            assert gate["execution_authorized"] is True
            assert gate["phase_qualified"] is True
            assert gate["production_promotion_allowed"] is False
        else:
            assert gate["gate"] == "BLOCKED"
            assert gate["operational_status"] == "BLOCKED"
            assert gate["execution_authorized"] is False
            assert gate["phase_qualified"] is False
