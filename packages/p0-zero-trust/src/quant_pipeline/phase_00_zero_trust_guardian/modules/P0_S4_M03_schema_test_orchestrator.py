from __future__ import annotations

from pathlib import Path

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s4_schema_oracle import execute_fixture_cases, load_registered_schemas
from ._p0_s4_test_evidence import artifact, created_at, digest, envelope, repository_root, require_call, validate_output


INPUTS = ["schema_registry", "fixtures_all_phases"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_call(inputs, config, INPUTS)
    registry = artifact(inputs["schema_registry"], "schema_registry")
    schemas = registry.get("schemas")
    fixture_container = inputs["fixtures_all_phases"]
    fixtures = fixture_container.get("fixtures") if isinstance(fixture_container, dict) else None
    if not isinstance(schemas, list) or not schemas or not isinstance(fixtures, list) or not fixtures:
        raise ContractValidationError("schema registry and fixtures must be non-empty inventories")
    repository = repository_root(Path(__file__), config)
    by_id = load_registered_schemas(schemas, repository)
    cases, coverage, mutation_classes = execute_fixture_cases(fixtures, by_id)
    missing = sorted(schema_id for schema_id, kinds in coverage.items() if kinds != {"valid", "invalid"})
    if missing:
        raise ContractValidationError(f"every registered schema requires valid and invalid fixtures: {missing}")
    failed = sum(case["status"] == "FAIL" for case in cases)
    fingerprint = digest(cases)
    report = {
        "artifact_id": f"schema-test-report-{fingerprint[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
        "schema_count": len(by_id),
        "fixture_count": len(cases),
        "passed_tests": len(cases) - failed,
        "failed_tests": failed,
        "tests": cases,
        "schemas_fully_covered": len(by_id) - len(missing),
        "schemas_partially_covered": len(missing),
        "mutation_class_count": len({kind for kinds in mutation_classes.values() for kind in kinds}),
        "valid_fixture_passes": all(case["status"] == "PASS" for case in cases if case["expectation"] == "valid"),
        "invalid_fixture_fails": all(case["status"] == "PASS" for case in cases if case["expectation"] == "invalid"),
        "status": "FAIL" if failed else "PASS",
        "release_blocking": bool(failed),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    validate_output(report, "schema_test_report.schema.yaml")
    return envelope("P0.S4.M03", "schema_test_orchestrator", INPUTS, {"schema_test_report": report})

