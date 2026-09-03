import json
import hashlib
from pathlib import Path
from tools.documentary_module_scope import documentary_status_paths


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def assert_bound_file(root: Path, binding: dict, hash_key: str = "sha256") -> Path:
    path = root / binding["path"]
    assert path.is_file(), path
    assert sha256(path) == binding[hash_key], path
    return path


def test_local_module_status_audit_is_complete_and_documentary_pass():
    root = workspace_root()
    report = json.loads((root / "reports/documentation/module_status_structural_audit.json").read_text(encoding="utf-8"))
    expected = len(documentary_status_paths(root))
    assert report["module_count"] == expected
    assert report["structural_pass_count"] == expected
    assert report["structural_fail_count"] == 0
    assert report["pending_status_count"] == 0
    blocked = sum(
        json.loads(path.read_text(encoding="utf-8")).get("status", "").lower() == "blocked"
        for path in documentary_status_paths(root)
    )
    assert report["pass_status_count"] == expected - blocked
    assert report["blocked_status_count"] == blocked
    assert report["promotion_allowed"] is False


def test_derived_phase_states_are_reconciled_to_documentary_pass():
    root = workspace_root()
    from tools.harness_snapshot import calculate_snapshot
    current = calculate_snapshot(root)["digest"]
    phase_statuses = sorted(root.glob("phases/*/phase_requirement_status.json"))
    gate_statuses = sorted(root.glob("phases/*/phase_gate_result.json"))
    assert len(phase_statuses) == 10
    assert len(gate_statuses) == 10
    assert (root / "phases/phase_00_zero_trust/phase_requirement_status.json").exists()
    assert (root / "phases/phase_00_zero_trust/phase_gate_result.json").exists()
    statuses = {path.parent.name: load(path) for path in phase_statuses}
    gates = {path.parent.name: load(path) for path in gate_statuses}
    for phase in ("phase_00_zero_trust", "phase_01_ingestion", "phase_02_quality_pit"):
        if statuses[phase].get("source_snapshot_digest") != current:
            assert statuses[phase]["status"] in {"BLOCKED", "PASS", "PHASE_QUALIFIED"}
            assert statuses[phase].get("production_promotion_allowed") is False
            assert gates[phase].get("production_promotion_allowed") is False
            continue
        assert statuses[phase]["status"] in {"PASS", "PHASE_QUALIFIED"}
        assert gates[phase]["status"] == "PASS"
    for phase in ("phase_03_agents_rag_memory", "phase_04_feature_base", "phase_05_underlying_forecasts", "phase_06_candidate_generation", "phase_07_ranking", "phase_08_portfolio_backtest", "phase_09_audit_learning"):
        assert statuses[phase]["status"] in {"BLOCKED", "IMPLEMENTED_LIMITED"}
        assert gates[phase]["status"] == "BLOCKED"

    # P0 may be implemented only when its local status and gate bind a real,
    # immutable PHASE_QUALIFIED verdict and the complete audit provenance.
    p0_status = statuses.pop("phase_00_zero_trust")
    p0_gate = gates.pop("phase_00_zero_trust")
    if p0_status.get("source_snapshot_digest") != current or p0_status.get("status") == "BLOCKED":
        assert p0_status["implementation_status"] == "IMPLEMENTED"
        assert p0_status["operational_status"] in {"PASS", "BLOCKED"}
        assert p0_gate["operational_gate"] in {"PASS", "BLOCKED"}
        assert p0_status["production_promotion_allowed"] is False
        assert p0_gate["production_promotion_allowed"] is False
        return
    assert p0_status["implementation_status"] == "IMPLEMENTED"
    assert p0_status["operational_status"] == "PASS"
    assert p0_gate["implementation_status"] == "IMPLEMENTED"
    assert p0_gate["operational_gate"] == "PASS"
    assert p0_status["production_promotion_allowed"] is False
    assert p0_gate["production_promotion_allowed"] is False
    assert p0_gate["source_file"] == "phases/phase_00_zero_trust/phase_requirement_status.json"
    assert p0_gate["source_sha256"] == sha256(root / p0_gate["source_file"])
    assert p0_status["snapshot_id"] == p0_gate["snapshot_id"]
    assert p0_status["qualification"] == p0_gate["qualification"]
    assert p0_status["independent_audit"] == p0_gate["independent_audit"]
    assert p0_status["operational_closure_audit"] == p0_gate["operational_closure_audit"]

    qualification = p0_status["qualification"]
    verdict_path = assert_bound_file(root, qualification, "verdict_sha256")
    verdict = load(verdict_path)
    assert verdict["phase_id"] == "P0"
    assert verdict["run_id"] == qualification["run_id"]
    assert verdict["final_status"] == "PHASE_QUALIFIED"
    assert verdict["production_promotion_allowed"] is False
    assert qualification["bundle_path"] == verdict_path.parent.relative_to(root).as_posix()
    assert qualification["module_evidence_set_digest"] == p0_status["snapshot_id"]
    independent = p0_status["independent_audit"]
    assert independent["path"] == f"reports/verification/p0_preclosure_audits/{qualification['run_id']}.json"
    assert independent["provenance"]["artifact_role"] == "immutable_run_specific_preclosure_audit"
    assert independent["provenance"]["run_id"] == qualification["run_id"]
    assert independent["provenance"]["target_canonical_bundle"] == qualification["bundle_path"]
    assert_bound_file(root, independent)
    assert_bound_file(root, p0_status["operational_closure_audit"])

    # Business phases remain fail-closed until separately authorized and
    # qualified; documentary PASS never authorizes their implementation.
    p1_status = statuses.pop("phase_01_ingestion")
    p1_gate = gates.pop("phase_01_ingestion")
    if p1_status.get("source_snapshot_digest") != current:
        assert p1_status["production_promotion_allowed"] is False
        assert p1_gate["production_promotion_allowed"] is False
        return
    assert p1_status["implementation_status"] == "IMPLEMENTED"
    assert p1_status["operational_status"] == "PASS"
    assert p1_gate["operational_gate"] == "PASS"
    p2_status = statuses.pop("phase_02_quality_pit")
    p2_gate = gates.pop("phase_02_quality_pit")
    if p2_status.get("source_snapshot_digest") != current:
        assert p2_status["implementation_status"] == "IMPLEMENTED"
        assert p2_status["operational_status"] == "BLOCKED"
        assert p2_gate["operational_gate"] == "BLOCKED"
        assert p2_status["production_promotion_allowed"] is False
        assert p2_gate["production_promotion_allowed"] is False
        return
    assert p2_status["implementation_status"] == "IMPLEMENTED"
    assert p2_status["operational_status"] == "PASS"
    assert p2_gate["operational_gate"] == "PASS"
    assert len(statuses) == len(gates) == 7
    for phase in ():
        assert statuses[phase]["implementation_status"] == "IMPLEMENTED"
        assert statuses[phase]["operational_status"] == "PASS"
        assert gates[phase]["operational_gate"] == "PASS"
    for phase in ("phase_03_agents_rag_memory", "phase_04_feature_base", "phase_05_underlying_forecasts", "phase_06_candidate_generation", "phase_07_ranking", "phase_08_portfolio_backtest", "phase_09_audit_learning"):
        assert statuses[phase]["implementation_status"] == "IMPLEMENTED"
        assert statuses[phase]["operational_status"] == "BLOCKED"
        assert gates[phase]["operational_gate"] == "BLOCKED"
    assert all(item.get("production_promotion_allowed") is False for item in statuses.values())
    assert all(item.get("production_promotion_allowed") is False for item in gates.values())
