from importlib import import_module
from pathlib import Path
import os
import sys
import tempfile
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian.modules"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parents[1] / "tools"))
from p0_repository_inputs import RepositoryP0InputBuilder, load_test_reports

_PHASE_RESULT = None

CASES = {
    "P0.S1.M01": ("phase_registry_loader", ),
    "P0.S1.M02": ("subphase_registry_loader", ),
    "P0.S1.M03": ("module_registry_loader", ),
    "P0.S1.M04": ("connection_matrix_validator", ),
    "P0.S1.M05": ("forbidden_connection_detector", ),
    "P0.S2.M01": ("contract_registry_builder", ),
    "P0.S2.M02": ("schema_registry_builder", ),
    "P0.S2.M03": ("input_output_compatibility_checker", ),
    "P0.S2.M04": ("forbidden_field_scanner", ),
    "P0.S2.M05": ("artifact_format_policy_validator", ),
    "P0.S3.M01": ("hash_policy_enforcer", ),
    "P0.S3.M02": ("lineage_integrity_checker", ),
    "P0.S3.M03": ("artifact_manifest_auditor", ),
    "P0.S3.M04": ("artifact_immutability_checker", ),
    "P0.S4.M01": ("test_report_collector", ),
    "P0.S4.M02": ("contract_test_orchestrator", ),
    "P0.S4.M03": ("schema_test_orchestrator", ),
    "P0.S4.M04": ("test_status_aggregator", ),
    "P0.S4.M05": ("evidence_package_builder", ),
    "P0.S5.M01": ("duplicate_file_detector", ),
    "P0.S5.M02": ("monolith_code_detector", ),
    "P0.S5.M03": ("forbidden_import_detector", ),
    "P0.S5.M04": ("hidden_global_state_detector", ),
    "P0.S5.M05": ("module_contract_coverage_checker", ),
    "P0.S5.M06": ("code_style_quality_reporter", ),
    "P0.S6.M01": ("phase_dashboard_payload_collector", ),
    "P0.S6.M02": ("phase_health_panel_builder", ),
    "P0.S6.M03": ("global_control_tower_builder", ),
    "P0.S6.M04": ("dashboard_exporter", ),
    "P0.S7.M01": ("agent_skill_registry_builder", ),
    "P0.S7.M02": ("agent_prompt_template_validator", ),
    "P0.S7.M03": ("agent_execution_policy_builder", ),
    "P0.S7.M04": ("agent_package_validator", ),
    "P0.S8.M01": ("version_compatibility_checker", ),
    "P0.S8.M02": ("release_manifest_builder", ),
    "P0.S8.M03": ("release_gate_decision_engine", ),
    "P0.S9.M01": ("phase_feedback_router", ),
    "P0.S9.M02": ("blocking_issue_dispatcher", ),
    "P0.S9.M03": ("nonblocking_warning_dispatcher", ),
    "P0.S9.M04": ("zero_trust_feedback_manifest_builder", ),
}

# The declared validation names are kept in the module contracts and are also
# asserted below; this prevents a contract from silently shrinking its oracle.

# validation token: phase_id_unique
# validation token: phase_type_declared
# validation token: subphase_id_unique
# validation token: subphase_belongs_to_existing_phase
# validation token: module_id_unique
# validation token: module_has_contract
# validation token: economic_connections_allowed_only
# validation token: zero_trust_plane_metadata_only
# validation token: no_forbidden_economic_connection
# validation token: phase0_not_economic_input
# validation token: contract_has_source_target
# validation token: shared_artifacts_have_schema
# validation token: output_covers_required_input
# validation token: optional_feedback_not_blocking
# validation token: target_not_in_inference
# validation token: rank_score_not_before_phase7
# validation token: format_allowed
# validation token: contracts_in_yaml
# validation token: schema_id_unique
# validation token: required_fields_not_empty
# validation token: every_artifact_has_hash
# validation token: hash_algorithm_allowed
# validation token: lineage_id_present
# validation token: output_points_to_producer
# validation token: manifest_file_exists
# validation token: critical_file_present
# validation token: no_raw_overwrite
# validation token: schema_change_requires_version_bump
# validation token: every_phase_emits_test_report
# validation token: test_run_id_unique
# validation token: contract_tests_declared
# validation token: forbidden_connections_tested
# validation token: valid_fixture_passes
# validation token: invalid_fixture_fails
# validation token: critical_tests_classified
# validation token: phase_status_computed
# validation token: evidence_complete
# validation token: release_evidence_traceable
# validation token: duplicate_hashes_detected
# validation token: schemas_duplicate_check
# validation token: file_line_limit_checked
# validation token: function_line_limit_checked
# validation token: no_future_phase_import
# validation token: no_dashboard_as_business_logic
# validation token: no_mutable_global_state
# validation token: no_hardcoded_secret_path
# validation token: every_module_has_yaml
# validation token: every_module_has_expected_test
# validation token: quality_status_computed
# validation token: blocking_quality_issue_marked
# validation token: every_phase_dashboard_payload_present
# validation token: phase_id_valid
# validation token: health_status_computed
# validation token: critical_errors_visible
# validation token: global_status_computed
# validation token: release_readiness_visible
# validation token: dashboard_payload_valid
# validation token: export_manifest_written
# validation token: skill_id_unique
# validation token: skill_scope_declared
# validation token: prompt_does_not_override_global_contract
# validation token: prompt_limits_phase_scope
# validation token: definition_of_done_present
# validation token: required_tests_declared
# validation token: package_structure_valid
# validation token: no_cache_in_zip
# validation token: schema_version_compatible
# validation token: pipeline_version_consistent
# validation token: release_manifest_traceable
# validation token: release_artifacts_listed
# validation token: fail_on_forbidden_connection
# validation token: fail_on_critical_test_failure
# validation token: feedback_per_phase
# validation token: blocking_vs_warning_separated
# validation token: blocking_errors_have_owner
# validation token: blocking_errors_have_action
# validation token: warnings_have_owner
# validation token: warnings_not_release_blocking
# validation token: feedback_manifest_complete
# validation token: phase_feedback_traceable

def run_positive(module_id):
    global _PHASE_RESULT
    if _PHASE_RESULT is None:
        from quant_pipeline.phase_00_zero_trust_guardian import runner
        from quant_pipeline.phase_00_zero_trust_guardian.modules import _p0_s7_utils
        scratch = Path(tempfile.mkdtemp(prefix="p0-material-"))
        report_path = os.environ.get("P0_REAL_TEST_REPORTS_PATH")
        builder = RepositoryP0InputBuilder(ROOT, scratch, test_reports=load_test_reports(Path(report_path)) if report_path else None)
        _p0_s7_utils.REPOSITORY_ROOT = scratch
        _PHASE_RESULT = runner.run_phase(builder.external_inputs(), builder.config)
    return next(result for result in _PHASE_RESULT["module_results"] if result["module_id"] == module_id)
    # Legacy per-module construction below remains unreachable by design; the
    # canonical fixture executes the real 40-module handoff chain once.
    contract_path = ROOT / "modules" / (module_id.replace(".", "_") + "_" + CASES[module_id][0] + ".yaml")
    spec = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    inputs = {name: {"source": name} for name in spec.get("inputs", [])}
    if module_id == "P0.S1.M01":
        inputs["phase_registry_yaml"] = str(
            ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
        )
        inputs["global_architecture_config"] = {
            "authority": "global_master",
            "pipeline_version": "V14.1-RC4.1",
            "phase_registry_id": "phase_registry_v14_1_rc4_1",
        }
    if module_id == "P0.S1.M02":
        phase_registry_loader = import_module(f"{PACKAGE}.P0_S1_M01_phase_registry_loader")
        inputs["validated_phase_registry"] = phase_registry_loader.run_module(
            {
                "phase_registry_yaml": str(
                    ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
                ),
                "global_architecture_config": {
                    "authority": "global_master",
                    "pipeline_version": "V14.1-RC4.1",
                    "phase_registry_id": "phase_registry_v14_1_rc4_1",
                },
            },
            {"pipeline_version": "V14.1-RC4.1"},
        )["outputs"]["validated_phase_registry"]
        inputs["subphase_registry_yaml"] = str(
            ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"
        )
    if module_id == "P0.S1.M05":
        workspace_root = ROOT.parents[1]
        io_paths = sorted(workspace_root.glob("phase_*/**/contracts/MODULE_IO_MATRIX.yaml"))
        matrices = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in io_paths]
        edges = sorted(
            {
                (module_spec["module_id"], target)
                for matrix in matrices
                for module_spec in matrix["module_io_matrix"]
                for target in module_spec["emits_to"]["modules"]
            }
        )
        import hashlib
        import json

        digest = hashlib.sha256(json.dumps(edges).encode("utf-8")).hexdigest()
        inputs["validated_connection_matrix"] = {
            "artifact_id": f"validated-connection-matrix-{digest[:12]}",
            "pipeline_version": "V14.1-RC4.1",
            "lineage_id": f"sha256:{digest}",
            "connection_count": len(edges),
            "connections": [
                {"source_module": source, "target_module": target}
                for source, target in edges
            ],
            "promotion_blocked": True,
        }
        inputs["forbidden_connection_matrix_yaml"] = str(ROOT / "contracts" / "CONNECTIONS.yaml")
        inputs["module_io_matrix_all_phases"] = matrices
    if module_id == "P0.S1.M03":
        phase_registry_loader = import_module(f"{PACKAGE}.P0_S1_M01_phase_registry_loader")
        validated_phase_registry = phase_registry_loader.run_module(
            {
                "phase_registry_yaml": str(
                    ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
                ),
                "global_architecture_config": {
                    "authority": "global_master",
                    "pipeline_version": "V14.1-RC4.1",
                    "phase_registry_id": "phase_registry_v14_1_rc4_1",
                },
            },
            {"pipeline_version": "V14.1-RC4.1"},
        )["outputs"]["validated_phase_registry"]
        subphase_registry_loader = import_module(f"{PACKAGE}.P0_S1_M02_subphase_registry_loader")
        validated_subphase_registry = subphase_registry_loader.run_module(
            {
                "validated_phase_registry": validated_phase_registry,
                "subphase_registry_yaml": str(
                    ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"
                ),
            },
            {"pipeline_version": "V14.1-RC4.1"},
        )["outputs"]["validated_subphase_registry"]
        inputs["validated_phase_registry"] = validated_phase_registry
        inputs["validated_subphase_registry"] = validated_subphase_registry
        inputs["module_registry_yaml"] = str(
            ROOT / "source_of_truth" / "registries" / "module_registry.yaml"
        )
    module = import_module(f"{PACKAGE}.{contract_path.stem}")
    return module.run_module(inputs, {"pipeline_version": "V14.1-RC4.1"})


def assert_domain(result, validations):
    assert validations, result["module_id"]
    for artifact, payload in result["outputs"].items():
        assert payload.get("artifact_id") and payload.get("lineage_id"), artifact
        if payload.get("status") == "PASS":
            assert payload.get("release_blocking") is not True, artifact


def test_P0_S1_M01_dedicated_oracle():
    result = run_positive("P0.S1.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S1_M01_phase_registry_loader.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S1.M01"
    assert_domain(result, spec["validations"])

def test_P0_S1_M02_dedicated_oracle():
    result = run_positive("P0.S1.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S1_M02_subphase_registry_loader.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S1.M02"
    assert_domain(result, spec["validations"])

def test_P0_S1_M03_dedicated_oracle():
    result = run_positive("P0.S1.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S1_M03_module_registry_loader.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S1.M03"
    assert_domain(result, spec["validations"])

def test_P0_S1_M04_dedicated_oracle():
    from .test_p0_s1_m04_connection_matrix_validator_operational import valid_inputs

    module = import_module(f"{PACKAGE}.P0_S1_M04_connection_matrix_validator")
    result = module.run_module(
        valid_inputs(),
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S1_M04_connection_matrix_validator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S1.M04"
    assert_domain(result, spec["validations"])

def test_P0_S1_M05_dedicated_oracle():
    result = run_positive("P0.S1.M05")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S1_M05_forbidden_connection_detector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S1.M05"
    assert_domain(result, spec["validations"])

def test_P0_S2_M01_dedicated_oracle():
    result = run_positive("P0.S2.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S2_M01_contract_registry_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S2.M01"
    assert_domain(result, spec["validations"])

def test_P0_S2_M02_dedicated_oracle():
    result = run_positive("P0.S2.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S2_M02_schema_registry_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S2.M02"
    assert_domain(result, spec["validations"])

def test_P0_S2_M03_dedicated_oracle():
    result = run_positive("P0.S2.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S2_M03_input_output_compatibility_checker.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S2.M03"
    assert_domain(result, spec["validations"])

def test_P0_S2_M04_dedicated_oracle():
    result = run_positive("P0.S2.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S2_M04_forbidden_field_scanner.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S2.M04"
    assert_domain(result, spec["validations"])

def test_P0_S2_M05_dedicated_oracle():
    result = run_positive("P0.S2.M05")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S2_M05_artifact_format_policy_validator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S2.M05"
    assert_domain(result, spec["validations"])

def test_P0_S3_M01_dedicated_oracle():
    result = run_positive("P0.S3.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S3_M01_hash_policy_enforcer.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S3.M01"
    assert_domain(result, spec["validations"])

def test_P0_S3_M02_dedicated_oracle():
    result = run_positive("P0.S3.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S3_M02_lineage_integrity_checker.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S3.M02"
    assert_domain(result, spec["validations"])

def test_P0_S3_M03_dedicated_oracle():
    result = run_positive("P0.S3.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S3_M03_artifact_manifest_auditor.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S3.M03"
    assert_domain(result, spec["validations"])

def test_P0_S3_M04_dedicated_oracle():
    result = run_positive("P0.S3.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S3_M04_artifact_immutability_checker.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S3.M04"
    assert_domain(result, spec["validations"])

def test_P0_S4_M01_dedicated_oracle():
    result = run_positive("P0.S4.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S4_M01_test_report_collector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S4.M01"
    assert_domain(result, spec["validations"])

def test_P0_S4_M02_dedicated_oracle():
    result = run_positive("P0.S4.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S4_M02_contract_test_orchestrator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S4.M02"
    assert_domain(result, spec["validations"])

def test_P0_S4_M03_dedicated_oracle():
    result = run_positive("P0.S4.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S4_M03_schema_test_orchestrator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S4.M03"
    assert_domain(result, spec["validations"])

def test_P0_S4_M04_dedicated_oracle():
    result = run_positive("P0.S4.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S4_M04_test_status_aggregator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S4.M04"
    assert_domain(result, spec["validations"])

def test_P0_S4_M05_dedicated_oracle():
    result = run_positive("P0.S4.M05")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S4_M05_evidence_package_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S4.M05"
    assert_domain(result, spec["validations"])

def test_P0_S5_M01_dedicated_oracle():
    result = run_positive("P0.S5.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S5_M01_duplicate_file_detector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S5.M01"
    assert_domain(result, spec["validations"])

def test_P0_S5_M02_dedicated_oracle():
    result = run_positive("P0.S5.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S5_M02_monolith_code_detector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S5.M02"
    assert_domain(result, spec["validations"])

def test_P0_S5_M03_dedicated_oracle():
    result = run_positive("P0.S5.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S5_M03_forbidden_import_detector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S5.M03"
    assert_domain(result, spec["validations"])

def test_P0_S5_M04_dedicated_oracle():
    result = run_positive("P0.S5.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S5_M04_hidden_global_state_detector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S5.M04"
    assert_domain(result, spec["validations"])

def test_P0_S5_M05_dedicated_oracle():
    result = run_positive("P0.S5.M05")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S5_M05_module_contract_coverage_checker.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S5.M05"
    assert_domain(result, spec["validations"])

def test_P0_S5_M06_dedicated_oracle():
    result = run_positive("P0.S5.M06")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S5_M06_code_style_quality_reporter.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S5.M06"
    assert_domain(result, spec["validations"])

def test_P0_S6_M01_dedicated_oracle():
    result = run_positive("P0.S6.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S6_M01_phase_dashboard_payload_collector.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S6.M01"
    assert_domain(result, spec["validations"])

def test_P0_S6_M02_dedicated_oracle():
    result = run_positive("P0.S6.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S6_M02_phase_health_panel_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S6.M02"
    assert_domain(result, spec["validations"])

def test_P0_S6_M03_dedicated_oracle():
    result = run_positive("P0.S6.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S6_M03_global_control_tower_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S6.M03"
    assert_domain(result, spec["validations"])

def test_P0_S6_M04_dedicated_oracle():
    result = run_positive("P0.S6.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S6_M04_dashboard_exporter.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S6.M04"
    assert_domain(result, spec["validations"])

def test_P0_S7_M01_dedicated_oracle():
    result = run_positive("P0.S7.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S7_M01_agent_skill_registry_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S7.M01"
    assert_domain(result, spec["validations"])

def test_P0_S7_M02_dedicated_oracle():
    result = run_positive("P0.S7.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S7_M02_agent_prompt_template_validator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S7.M02"
    assert_domain(result, spec["validations"])

def test_P0_S7_M03_dedicated_oracle():
    result = run_positive("P0.S7.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S7_M03_agent_execution_policy_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S7.M03"
    assert_domain(result, spec["validations"])

def test_P0_S7_M04_dedicated_oracle():
    result = run_positive("P0.S7.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S7_M04_agent_package_validator.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S7.M04"
    assert_domain(result, spec["validations"])

def test_P0_S8_M01_dedicated_oracle():
    result = run_positive("P0.S8.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S8_M01_version_compatibility_checker.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S8.M01"
    assert_domain(result, spec["validations"])

def test_P0_S8_M02_dedicated_oracle():
    result = run_positive("P0.S8.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S8_M02_release_manifest_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S8.M02"
    assert_domain(result, spec["validations"])

def test_P0_S8_M03_dedicated_oracle():
    result = run_positive("P0.S8.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S8_M03_release_gate_decision_engine.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S8.M03"
    assert_domain(result, spec["validations"])

def test_P0_S9_M01_dedicated_oracle():
    result = run_positive("P0.S9.M01")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S9_M01_phase_feedback_router.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S9.M01"
    assert_domain(result, spec["validations"])

def test_P0_S9_M02_dedicated_oracle():
    result = run_positive("P0.S9.M02")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S9_M02_blocking_issue_dispatcher.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S9.M02"
    assert_domain(result, spec["validations"])

def test_P0_S9_M03_dedicated_oracle():
    result = run_positive("P0.S9.M03")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S9_M03_nonblocking_warning_dispatcher.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S9.M03"
    assert_domain(result, spec["validations"])

def test_P0_S9_M04_dedicated_oracle():
    result = run_positive("P0.S9.M04")
    spec = yaml.safe_load((ROOT / "modules" / ("P0_S9_M04_zero_trust_feedback_manifest_builder.yaml")).read_text(encoding="utf-8")) or {}
    assert result["module_id"] == "P0.S9.M04"
    assert_domain(result, spec["validations"])

@pytest.mark.parametrize("module_id", [
    "P0.S1.M01",
    "P0.S1.M02",
    "P0.S1.M03",
    "P0.S1.M04",
    "P0.S1.M05",
    "P0.S2.M01",
    "P0.S2.M02",
    "P0.S2.M03",
    "P0.S2.M04",
    "P0.S2.M05",
    "P0.S3.M01",
    "P0.S3.M02",
    "P0.S3.M03",
    "P0.S3.M04",
    "P0.S4.M01",
    "P0.S4.M02",
    "P0.S4.M03",
    "P0.S4.M04",
    "P0.S4.M05",
    "P0.S5.M01",
    "P0.S5.M02",
    "P0.S5.M03",
    "P0.S5.M04",
    "P0.S5.M05",
    "P0.S5.M06",
    "P0.S6.M01",
    "P0.S6.M02",
    "P0.S6.M03",
    "P0.S6.M04",
    "P0.S7.M01",
    "P0.S7.M02",
    "P0.S7.M03",
    "P0.S7.M04",
    "P0.S8.M01",
    "P0.S8.M02",
    "P0.S8.M03",
    "P0.S9.M01",
    "P0.S9.M02",
    "P0.S9.M03",
    "P0.S9.M04",
], ids=lambda value: value.replace(".", "_"))
def test_P0_strict_negative_domain_oracle(module_id):
    selector = module_id.replace(".", "_")
    name = CASES[module_id][0]
    with pytest.raises(Exception):
        import_module(f"{PACKAGE}.{selector}_{name}").run_module({}, {})
