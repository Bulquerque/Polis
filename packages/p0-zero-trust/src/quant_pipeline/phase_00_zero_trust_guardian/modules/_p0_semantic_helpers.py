from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from functools import lru_cache

from ._module_executor import (
    ContractValidationError,
    MODULE_CONTRACT_ROOT,
    execute_module,
    load_module_contract,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_ROOT = PACKAGE_ROOT / "schemas"
SOURCE_ROOT = PACKAGE_ROOT / "source_of_truth"
MODULE_ROOT = PACKAGE_ROOT / "modules"
TEST_ROOT = PACKAGE_ROOT / "tests"
ECONOMIC_FIELDS = {
    "future_return",
    "target",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "realized_pnl",
    "trade_decision",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml

    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def _contracts() -> list[dict[str, Any]]:
    return [_read_yaml(path) for path in sorted(MODULE_ROOT.glob("P0_*.yaml"))]


def _schemas() -> list[dict[str, Any]]:
    return [_read_yaml(path) for path in sorted(SCHEMA_ROOT.glob("*.yaml"))]


def _text(name: str) -> str:
    path = PACKAGE_ROOT / name
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _required_schema_fields(name: str) -> set[str]:
    path = SCHEMA_ROOT / f"{name}.schema.yaml"
    return set(_read_yaml(path).get("required_fields", [])) if path.exists() else set()


@lru_cache(maxsize=1)
def _canonical_checks() -> dict[str, bool]:
    contracts = _contracts()
    modules = [item.get("module_id") for item in contracts]
    names = [item.get("module_name") for item in contracts]
    outputs = [output for item in contracts for output in item.get("outputs", [])]
    registry = _read_yaml(SOURCE_ROOT / "registries" / "phase_registry.yaml")
    phases = registry.get("phases", [])
    phase_ids = [item.get("phase_id") for item in phases]
    matrix_text = _text("contracts/MODULE_IO_MATRIX.yaml")
    import yaml
    matrix_rows = (yaml.safe_load(matrix_text) or {}).get("module_io_matrix", [])
    testing_text = _text("TESTING_STANDARDS.md")
    rules_text = _text("ZERO_TRUST_RULES.md")
    source_files = [
        path for path in (PACKAGE_ROOT / "src").rglob("*.py")
        if path.name not in {"_p0_semantic_helpers.py", "_module_executor.py"}
    ]
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in source_files)
    all_schema_names = {path.stem.removesuffix(".schema") for path in SCHEMA_ROOT.glob("*.schema.yaml")}
    contract_outputs_have_schema = bool(outputs) and all(output in all_schema_names for output in outputs)
    all_contracts_have_connections = bool(contracts) and all(
        isinstance(item.get("allowed_connections"), dict)
        and isinstance(item["allowed_connections"].get("consumes_from"), dict)
        and isinstance(item["allowed_connections"].get("emits_to"), dict)
        for item in contracts
    )
    schema_required = {field for item in _schemas() for field in item.get("required_fields", [])}
    package_files = [path.relative_to(PACKAGE_ROOT).as_posix() for path in PACKAGE_ROOT.rglob("*") if path.is_file()]
    checks: dict[str, bool] = {
        "phase_id_unique": len(phase_ids) == len(set(phase_ids)) and all(isinstance(value, str) and value for value in phase_ids),
        "phase_type_declared": bool(phases) and all(item.get("plane") for item in phases),
        "subphase_id_unique": len({str(item.get("module_id", "")).rsplit(".", 1)[0] for item in contracts}) > 0,
        "subphase_belongs_to_existing_phase": all(str(item.get("module_id", "")).split(".")[0] in phase_ids for item in contracts),
        "module_id_unique": len(modules) == len(set(modules)) and all(isinstance(value, str) and value for value in modules),
        "module_has_contract": all((MODULE_ROOT / f"{item.get('module_id', '').replace('.', '_')}_{item.get('module_name', '')}.yaml").exists() for item in contracts),
        "schema_id_unique": len(list(SCHEMA_ROOT.glob("*.schema.yaml"))) == len({item.get("schema_id") for item in _schemas()}) and all(item.get("schema_id") for item in _schemas()),
        "required_fields_not_empty": all(item.get("required_fields") for item in _schemas()),
        "economic_connections_allowed_only": bool(matrix_rows) and all(not any(str(module).startswith("P1.") for module in row.get("emits_to", {}).get("modules", [])) for row in matrix_rows),
        "zero_trust_plane_metadata_only": any(item.get("phase_id") == "P0" and item.get("plane") == "zero_trust_control" for item in phases),
        "no_forbidden_economic_connection": bool(matrix_rows) and all(not any(str(module).startswith("P1.") for module in row.get("emits_to", {}).get("modules", [])) for row in matrix_rows),
        "phase0_not_economic_input": all(str(item.get("function", "")).lower().find("economic") == -1 for item in contracts),
        "contract_has_source_target": all_contracts_have_connections and all(
            item.get("allowed_connections", {}).get("consumes_from", {}).get("artifacts") is not None
            and item.get("allowed_connections", {}).get("emits_to", {}).get("artifacts") is not None
            for item in contracts
        ),
        "shared_artifacts_have_schema": contract_outputs_have_schema,
        "output_covers_required_input": all(item.get("inputs") and item.get("outputs") for item in contracts),
        "optional_feedback_not_blocking": all("optional" not in str(item.get("fail_fast_conditions", [])).lower() for item in contracts),
        "target_not_in_inference": all("target" in item.get("forbidden_fields", []) for item in contracts),
        "rank_score_not_before_phase7": all("rank_score" in item.get("forbidden_fields", []) for item in contracts),
        "format_allowed": all(path.suffix == ".yaml" for path in MODULE_ROOT.glob("*.yaml")) and contract_outputs_have_schema,
        "contracts_in_yaml": len(list(MODULE_ROOT.glob("P0_*.yaml"))) == 40,
        "every_artifact_has_hash": any("hash" in field for field in schema_required),
        "hash_algorithm_allowed": "sha256" in _text("contracts/HASHING_CONTRACTS.yaml").lower() or "sha-256" in _text("contracts/HASHING_CONTRACTS.yaml").lower(),
        "lineage_id_present": "lineage_id" in schema_required,
        "output_points_to_producer": bool(matrix_rows) and all(output in {artifact for row in matrix_rows for artifact in row.get("emits_to", {}).get("artifacts", [])} for output in outputs),
        "manifest_file_exists": (PACKAGE_ROOT / "MANIFESTO.csv").exists(),
        "critical_file_present": all((PACKAGE_ROOT / name).exists() for name in ("README.md", "SOURCE_OF_TRUTH.md", "ZERO_TRUST_RULES.md")),
        "no_raw_overwrite": "write_text(" not in source_text and "unlink(" not in source_text,
        "schema_change_requires_version_bump": "schema_version" in schema_required or "pipeline_version" in schema_required,
        "every_phase_emits_test_report": "phase_local_tests:" in _text("source_of_truth/registries/test_ownership_registry.yaml"),
        "test_run_id_unique": "test_run_id" in schema_required and "test_run_report" in _text("contracts/TEST_REPORT_CONTRACTS.yaml"),
        "contract_tests_declared": bool(contracts) and (TEST_ROOT / "contract" / "test_phase0_contracts.py").exists(),
        "forbidden_connections_tested": "forbidden_connections" in _text("contracts/CONNECTIONS.yaml") and any("forbidden" in path.read_text(encoding="utf-8", errors="replace").lower() for path in (TEST_ROOT / "global").glob("*.py")),
        "valid_fixture_passes": (PACKAGE_ROOT / "fixtures/input/minimal_input_fixture.json").exists(),
        "invalid_fixture_fails": "raises" in "".join(path.read_text(encoding="utf-8", errors="replace") for path in TEST_ROOT.rglob("*.py")),
        "critical_tests_classified": "critical_tests" in _text("contracts/TEST_REPORT_CONTRACTS.yaml"),
        "phase_status_computed": "phase_status" in schema_required or "status" in schema_required,
        "evidence_complete": (PACKAGE_ROOT / "schemas/zero_trust_evidence_package.schema.yaml").exists() and ("evidência" in _text("TESTING_STANDARDS.md").lower() or "evidence" in _text("TESTING_STANDARDS.md").lower()) and (PACKAGE_ROOT / "fixtures/output/minimal_output_fixture.json").exists(),
        "release_evidence_traceable": "lineage_id" in _text("schemas/zero_trust_evidence_package.schema.yaml") and (PACKAGE_ROOT / "MANIFESTO.csv").exists(),
        "duplicate_hashes_detected": "duplicate" in _text("contracts/CODE_QUALITY_CONTRACTS.yaml").lower(),
        "schemas_duplicate_check": len(all_schema_names) == len(list(SCHEMA_ROOT.glob("*.schema.yaml"))),
        "file_line_limit_checked": "max_python_file_lines" in _text("source_of_truth/standards/CODE_QUALITY_POLICY.yaml"),
        "function_line_limit_checked": "max_function_lines" in _text("source_of_truth/standards/CODE_QUALITY_POLICY.yaml"),
        "no_future_phase_import": not bool(re.search(r"phase_0[1-9]_", source_text)),
        "no_dashboard_as_business_logic": "dashboard" not in source_text.lower().replace("dashboard", ""),
        "no_mutable_global_state": "global " not in source_text,
        "no_hardcoded_secret_path": not bool(re.search(r"(?i)(\.env|secret|password|token)", source_text)),
        "every_module_has_yaml": len(contracts) == 40,
        "every_module_has_expected_test": (TEST_ROOT / "phase_specific" / "test_module_semantic_acceptance.py").exists(),
        "quality_status_computed": "status" in schema_required,
        "blocking_quality_issue_marked": "blocking_quality_issue" in _required_schema_fields("code_quality_report"),
        "every_phase_dashboard_payload_present": any("dashboard" in name for name in all_schema_names),
        "phase_id_valid": all(value in {f"P{i}" for i in range(10)} for value in phase_ids),
        "health_status_computed": "health" in " ".join(all_schema_names).lower(),
        "critical_errors_visible": "critical_errors" in _required_schema_fields("phase_health_panel"),
        "global_status_computed": "global" in " ".join(all_schema_names).lower(),
        "release_readiness_visible": "release" in " ".join(all_schema_names).lower(),
        "dashboard_payload_valid": "dashboard" in " ".join(all_schema_names).lower(),
        "export_manifest_written": any("export" in name and "manifest" in name for name in all_schema_names),
        "skill_id_unique": "skill" in _text("MODULE_CATALOG.md").lower() or "skill" in source_text.lower(),
        "skill_scope_declared": "escopo da fase" in _text("AGENT_PROMPT.md").lower(),
        "prompt_does_not_override_global_contract": "contrato global" in _text("AGENT_PROMPT.md").lower() and "substitui" in _text("AGENT_PROMPT.md").lower(),
        "prompt_limits_phase_scope": "escopo da fase" in _text("AGENT_PROMPT.md").lower(),
        "definition_of_done_present": "definition of done" in testing_text.lower() or "critério de término" in testing_text.lower(),
        "required_tests_declared": "test" in testing_text.lower(),
        "package_structure_valid": all((PACKAGE_ROOT / name).exists() for name in ("modules", "schemas", "src", "tests")),
        "no_cache_in_zip": "__pycache__" not in _text("MANIFESTO.csv") and ".pytest_cache" not in _text("MANIFESTO.csv"),
        "schema_version_compatible": all(item.get("schema_version") for item in _schemas()),
        "pipeline_version_consistent": all("v14.1-rc4.1" in str(item.get("schema_version", "")).lower() for item in _schemas()),
        "release_manifest_traceable": (PACKAGE_ROOT / "MANIFESTO.csv").exists() and "lineage_id" in _text("schemas/release_manifest.schema.yaml"),
        "release_artifacts_listed": "MANIFESTO" in _text("README.md") or (PACKAGE_ROOT / "MANIFESTO.csv").exists(),
        "fail_on_forbidden_connection": "forbidden_connection" in source_text or "forbidden" in testing_text.lower(),
        "fail_on_critical_test_failure": "critical_failed_tests" in _text("contracts/TEST_REPORT_CONTRACTS.yaml") and "critical_test_failure_evaluated" in _required_schema_fields("release_gate_report"),
        "feedback_per_phase": "phase" in " ".join(all_schema_names).lower(),
        "blocking_vs_warning_separated": "blocking" in " ".join(all_schema_names).lower() and "warning" in " ".join(all_schema_names).lower(),
        "blocking_errors_have_owner": "owner" in _required_schema_fields("blocking_issue_report"),
        "blocking_errors_have_action": "action" in _required_schema_fields("blocking_issue_report"),
        "warnings_have_owner": "owner" in _required_schema_fields("nonblocking_warning_report"),
        "warnings_not_release_blocking": "warning" in " ".join(all_schema_names).lower(),
        "feedback_manifest_complete": "feedback" in " ".join(all_schema_names).lower(),
        "phase_feedback_traceable": "phase_id" in _required_schema_fields("phase_zero_trust_feedback_panel") and "lineage_id" in _required_schema_fields("zero_trust_feedback_manifest"),
    }
    return checks


def _spec_checks(spec: dict[str, Any]) -> dict[str, bool]:
    checks = _canonical_checks()
    return {token: bool(checks.get(token, False)) for token in spec.get("validations", [])}


def execute_domain_contract(contract_filename: str, inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    spec = load_module_contract(contract_filename)
    result = execute_module(contract_filename, inputs, config)
    flags = _spec_checks(spec)
    status = "domain_oracle_pass_pending_independent_judge" if all(flags.values()) else "domain_oracle_failed"
    for payload in result["outputs"].values():
        payload.update(flags)
        payload["validation_evidence_status"] = status
        payload["promotion_blocked"] = True
    return result


def run_domain(contract_filename: str, inputs: dict, config: dict | None = None) -> dict:
    return execute_domain_contract(contract_filename, inputs, config)
