from __future__ import annotations

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s4_contract_oracle import build_contract_cases
from ._p0_s4_test_evidence import artifact, created_at, digest, envelope, require_call, validate_output


INPUTS = ["contract_registry", "schema_registry", "validated_module_registry"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_call(inputs, config, INPUTS)
    contracts_artifact = artifact(inputs["contract_registry"], "contract_registry")
    schemas_artifact = artifact(inputs["schema_registry"], "schema_registry")
    modules_artifact = artifact(inputs["validated_module_registry"], "validated_module_registry")
    contracts = contracts_artifact.get("contracts")
    schemas = schemas_artifact.get("schemas")
    modules = modules_artifact.get("modules")
    mirrors = schemas_artifact.get("mirrors", [])
    if not all(isinstance(value, list) and value for value in (contracts, schemas, modules)):
        raise ContractValidationError("registries must contain non-empty material inventories")
    if not isinstance(mirrors, list):
        raise ContractValidationError("schema registry mirrors must be a list")
    cases = build_contract_cases(contracts, schemas, modules, mirrors)
    if not cases:
        raise ContractValidationError("no contract tests were generated")
    failed = sum(case["status"] == "FAIL" for case in cases)
    fingerprint = digest(cases)
    common = {
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
    }
    plan = {
        "artifact_id": f"contract-test-plan-{fingerprint[:12]}",
        **common,
        "contract_count": len(contracts),
        "test_count": len(cases),
        "tests": [{k: v for k, v in case.items() if k != "status"} for case in cases],
        "contract_tests_declared": True,
        "connection_contracts_tested": True,
        "forbidden_connections_tested": False,
        "forbidden_policy_delegated_to": "P0.S1.M05",
    }
    report = {
        "artifact_id": f"contract-test-report-{fingerprint[:12]}",
        **common,
        "contract_count": len(contracts),
        "total_tests": len(cases),
        "passed_tests": len(cases) - failed,
        "failed_tests": failed,
        "tests": cases,
        "status": "FAIL" if failed else "PASS",
        "release_blocking": bool(failed),
        "contract_tests_declared": True,
        "connection_contracts_tested": True,
        "forbidden_connections_tested": False,
        "forbidden_policy_delegated_to": "P0.S1.M05",
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    validate_output(plan, "contract_test_execution_plan.schema.yaml")
    validate_output(report, "contract_test_report.schema.yaml")
    return envelope(
        "P0.S4.M02",
        "contract_test_orchestrator",
        INPUTS,
        {"contract_test_execution_plan": plan, "contract_test_report": report},
    )
