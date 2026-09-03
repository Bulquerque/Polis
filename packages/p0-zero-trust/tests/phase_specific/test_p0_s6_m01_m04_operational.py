from __future__ import annotations

from importlib import import_module
from pathlib import Path
import hashlib
import json
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def mod(number: int, name: str):
    return import_module(f"quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S6_M{number:02d}_{name}")


M01 = mod(1, "phase_dashboard_payload_collector")
M02 = mod(2, "phase_health_panel_builder")
M03 = mod(3, "global_control_tower_builder")
M04 = mod(4, "dashboard_exporter")


def report(name: str, status: str = "PASS", **extra):
    value = {
        "artifact_id": name,
        "lineage_id": "sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        "status": status,
        "release_blocking": status == "FAIL",
    }
    value.update(extra)
    return value


def phase_payload(phase_id: str, *, qualified: bool = True, status: str = "PASS"):
    return report(
        f"dashboard-{phase_id}",
        status,
        phase_id=phase_id,
        phase_name=f"Phase {phase_id}",
        development_status="IMPLEMENTED",
        test_status="PASS",
        health_status="HEALTHY" if status == "PASS" else "CRITICAL",
        qualification_status="QUALIFIED" if qualified else "ELIGIBLE",
        documentation_status="READY",
        module_counts={"planned": 4, "implemented": 4, "tested": 4, "qualified": 4 if qualified else 0},
        subphase_counts={"planned": 1, "implemented": 1, "tested": 1, "qualified": 1 if qualified else 0},
        issue_counts={"critical": 0, "warning": 0, "notice": 0},
    )


def inputs_m01(phases=None):
    if phases is None:
        phases = [phase_payload(f"P{i}") for i in range(10)]
    return {
        "dashboard_phase_payload_all_phases": {"phases": phases},
        "phase_test_status_panel": report("test-panel", phases=[{"phase_id": f"P{i}", "status": "PASS"} for i in range(10)]),
        "artifact_manifest_audit_report": report("manifest-audit"),
    }


def chain(phases=None):
    collected = M01.run_module(inputs_m01(phases), {"created_at": "2026-07-22T00:00:00Z"})["outputs"]["collected_phase_dashboard_payloads"]
    panel = M02.run_module(
        {
            "collected_phase_dashboard_payloads": collected,
            "global_test_report": report("global-tests"),
            "code_quality_report": report("quality"),
            "hash_integrity_report": report("hashes"),
        },
        {"created_at": "2026-07-22T00:00:00Z"},
    )["outputs"]["phase_health_panel"]
    tower_outputs = M03.run_module(
        {
            "phase_health_panel": panel,
            "forbidden_connection_report": report("connections"),
            "io_compatibility_report": report("io"),
            "zero_trust_evidence_package": report("evidence", schema_status="PASS"),
        },
        {"created_at": "2026-07-22T00:00:00Z"},
    )["outputs"]
    return collected, panel, tower_outputs


def test_complete_project_is_ready_without_conflating_health_and_readiness():
    collected, panel, outputs = chain()
    assert collected["phase_count"] == 10
    assert panel["readiness_status"] == "READY"
    assert panel["health_status"] == "HEALTHY"
    assert outputs["global_control_tower_payload"]["release_readiness"] == "READY"
    assert outputs["global_control_tower_payload"]["status"] == "PASS"


def test_partial_project_synthesizes_not_started_phases_without_calling_them_failures():
    data = inputs_m01([phase_payload("P0")])
    data["dashboard_phase_payload_all_phases"]["registry_snapshot"] = {"phases": [{"phase_id": f"P{i}"} for i in range(10)]}
    collected = M01.run_module(data)["outputs"]["collected_phase_dashboard_payloads"]
    p1 = next(x for x in collected["phases"] if x["phase_id"] == "P1")
    assert p1["development_status"] == "NOT_STARTED"
    assert p1["health_status"] == "UNKNOWN"
    assert p1["status"] == "PASS"
    assert p1["readiness"] == "NOT_READY"
    panel = M02.run_module({
        "collected_phase_dashboard_payloads": collected,
        "global_test_report": report("g"),
        "code_quality_report": report("q"),
        "hash_integrity_report": report("h"),
    })["outputs"]["phase_health_panel"]
    assert panel["status"] == "PASS"
    assert panel["readiness_status"] == "NOT_READY"
    assert panel["release_blocking"] is False
    assert not panel["critical_errors"]


def test_state_conflict_is_visible_but_canonical_qualification_wins():
    data = inputs_m01()
    data["dashboard_phase_payload_all_phases"]["phases"][0]["qualification_status"] = "ELIGIBLE"
    data["dashboard_phase_payload_all_phases"]["qualification_state_snapshot"] = {
        "phases": {"P0": {"qualification_status": "PHASE_QUALIFIED"}}
    }
    collected = M01.run_module(data)["outputs"]["collected_phase_dashboard_payloads"]
    p0 = collected["phases"][0]
    assert p0["qualification_status"] == "QUALIFIED"
    assert collected["source_freshness"] == "CONFLICTING"
    assert collected["state_conflicts"]
    assert collected["status"] == "PASS"


def test_m03_schema_status_does_not_alias_io_status_and_hash_comes_from_hash_report():
    _, panel, _ = chain()
    outputs = M03.run_module({
        "phase_health_panel": panel,
        "forbidden_connection_report": report("connections"),
        "io_compatibility_report": report("io", "FAIL"),
        "zero_trust_evidence_package": report("evidence", schema_status="PASS"),
    })["outputs"]
    tower = outputs["global_control_tower_payload"]
    assert tower["schema_status"] == "PASS"
    assert tower["hash_status"] == "PASS"
    assert tower["zero_trust_summary"]["io_compatibility"] == "FAIL"


def test_real_dashboard_files_are_materialized_and_hashes_match(tmp_path):
    _, panel, outputs = chain()
    exported = M04.run_module(
        {"global_control_tower_payload": outputs["global_control_tower_payload"], "phase_health_panel": panel},
        {"dashboard_output_dir": str(tmp_path), "created_at": "2026-07-22T00:00:00Z"},
    )["outputs"]
    manifest = exported["dashboard_export_manifest"]
    assert manifest["entry_count"] == 4
    assert exported["dashboard_static_site"]["materialized"] is True
    for entry in manifest["entries"]:
        path = tmp_path / entry["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert "P0 — Global Control Tower" in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_dashboard_output_is_deterministic_across_output_roots(tmp_path):
    _, panel, outputs = chain()
    config = {"created_at": "2026-07-22T00:00:00Z"}
    a = M04.run_module(
        {"global_control_tower_payload": outputs["global_control_tower_payload"], "phase_health_panel": panel},
        {**config, "dashboard_output_dir": str(tmp_path / "a")},
    )["outputs"]
    b = M04.run_module(
        {"global_control_tower_payload": outputs["global_control_tower_payload"], "phase_health_panel": panel},
        {**config, "dashboard_output_dir": str(tmp_path / "b")},
    )["outputs"]
    assert a["dashboard_static_site"]["content_sha256"] == b["dashboard_static_site"]["content_sha256"]
    assert a["dashboard_export_manifest"]["entries"] == b["dashboard_export_manifest"]["entries"]


def test_critical_runtime_failure_propagates_but_not_started_is_only_not_ready():
    phases = [phase_payload(f"P{i}") for i in range(10)]
    phases[4] = phase_payload("P4", status="FAIL")
    collected, panel, towers = chain(phases)
    assert collected["status"] == "FAIL"
    assert panel["health_status"] == "CRITICAL"
    assert towers["global_control_tower_payload"]["status"] == "FAIL"
    assert towers["global_control_tower_payload"]["release_readiness"] == "BLOCKED"


def test_forged_lineage_is_rejected_on_source_and_s6_boundaries():
    data = inputs_m01()
    data["dashboard_phase_payload_all_phases"]["phases"][0]["lineage_id"] = "forged"
    with pytest.raises(ValueError, match="lineage_id"):
        M01.run_module(data)
    _, panel, outputs = chain()
    panel["lineage_id"] = "sha256:short"
    with pytest.raises(ValueError, match="lineage_id"):
        M03.run_module({
            "phase_health_panel": panel,
            "forbidden_connection_report": report("c"),
            "io_compatibility_report": report("i"),
            "zero_trust_evidence_package": report("z"),
        })
    panel = chain()[1]
    outputs["global_control_tower_payload"]["lineage_id"] = "fake"
    with pytest.raises(ValueError, match="lineage_id"):
        M04.run_module({"global_control_tower_payload": outputs["global_control_tower_payload"], "phase_health_panel": panel})


def test_recursive_forbidden_fields_are_rejected():
    data = inputs_m01()
    data["phase_test_status_panel"]["nested"] = {"rank_score": 1}
    with pytest.raises(ValueError, match="forbidden input fields"):
        M01.run_module(data)


def test_all_outputs_match_their_exact_schemas():
    collected, panel, towers = chain()
    exports = M04.run_module({"global_control_tower_payload": towers["global_control_tower_payload"], "phase_health_panel": panel})["outputs"]
    cases = [(collected, "collected_phase_dashboard_payloads"), (panel, "phase_health_panel")]
    cases.extend((value, name) for name, value in towers.items())
    cases.extend((value, name) for name, value in exports.items())
    for artifact, name in cases:
        schema = yaml.safe_load((ROOT / "schemas" / f"{name}.schema.yaml").read_text(encoding="utf-8"))
        assert set(artifact) == set(schema["properties"]) == set(schema["required_fields"])


def test_payload_json_is_valid_and_contains_no_absolute_output_path(tmp_path):
    _, panel, outputs = chain()
    exported = M04.run_module(
        {"global_control_tower_payload": outputs["global_control_tower_payload"], "phase_health_panel": panel},
        {"dashboard_output_dir": str(tmp_path)},
    )["outputs"]
    data = json.loads((tmp_path / "data/control_tower.json").read_text(encoding="utf-8"))
    assert data["control_tower"]["phase_count"] == 10
    serialized = json.dumps(exported, sort_keys=True)
    assert str(tmp_path) not in serialized
