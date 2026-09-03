from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import forbidden_fields
from ._p0_s1_common import (
    created_at,
    find_forbidden_fields,
    module_result,
    normalized_version,
    require_inputs,
    stable_digest,
    validate_output,
)
from ._p0_s1_global_topology import build_global_topology, load_io_matrices
from ._p0_s1_policy import finding, load_policy, rule_matches, validated_edges


MODULE_ID = "P0.S1.M05"
MODULE_NAME = "forbidden_connection_detector"
CONTRACT = "P0_S1_M05_forbidden_connection_detector.yaml"
REQUIRED_INPUTS = [
    "validated_connection_matrix",
    "forbidden_connection_matrix_yaml",
    "module_io_matrix_all_phases",
]
OUTPUT_NAME = "forbidden_connection_report"


def _phase_id(module_id: str) -> str:
    return module_id.split(".", 1)[0]


def _expected_validated_edges(
    validated: set[tuple[str, str]],
    declared: set[tuple[str, str]],
    scope_phase: str | None,
) -> set[tuple[str, str]]:
    if scope_phase:
        return {edge for edge in declared if _phase_id(edge[0]) == scope_phase}
    # Backward-compatible fallback for legacy validated artifacts without explicit scope.
    if any(_phase_id(source) != "P0" for source, _ in validated):
        return declared
    return {edge for edge in declared if _phase_id(edge[0]) == "P0"}


def _matrix_findings(
    *,
    topology: dict[str, Any],
    validated: set[tuple[str, str]],
    expected: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    modules = topology["modules"]
    emit_edges = topology["emit_edges"]
    consume_edges = topology["consume_edges"]
    for source, target in sorted(emit_edges | consume_edges):
        if source not in modules or target not in modules:
            findings.append(
                finding(
                    "UNKNOWN_MODULE_REFERENCE",
                    source,
                    target,
                    "*",
                    "IO matrix references a module that is not declared",
                )
            )
    for source, target in sorted(emit_edges.symmetric_difference(consume_edges)):
        findings.append(
            finding(
                "IO_MATRIX_ASYMMETRY",
                source,
                target,
                "*",
                "Emitter and consumer declarations do not agree",
            )
        )
    for source, target in sorted(validated - expected):
        findings.append(
            finding(
                "UNDECLARED_VALIDATED_EDGE",
                source,
                target,
                "*",
                "Validated connection is absent from the bidirectional IO declarations",
            )
        )
    for source, target in sorted(expected - validated):
        findings.append(
            finding(
                "VALIDATED_EDGE_MISSING",
                source,
                target,
                "*",
                "Bidirectionally declared IO connection is absent from the validated matrix",
            )
        )
    return findings


def _policy_findings(
    declared: set[tuple[str, str]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for edge in sorted(declared):
        for rule in rules:
            if rule_matches(rule, edge):
                findings.append(
                    finding(
                        "EXPLICIT_FORBIDDEN_CONNECTION",
                        edge[0],
                        edge[1],
                        "*",
                        rule["message"],
                    )
                )
        if _phase_id(edge[0]) == "P0" and _phase_id(edge[1]) != "P0":
            findings.append(
                finding(
                    "P0_ECONOMIC_INPUT",
                    edge[0],
                    edge[1],
                    "*",
                    "A Phase 0 module is used as an input by an economic phase",
                )
            )
    return findings


def _p0_artifact_findings(topology: dict[str, Any]) -> list[dict[str, Any]]:
    p0_artifacts = {
        artifact
        for module_id, artifacts in topology["produced_artifacts"].items()
        if _phase_id(module_id) == "P0"
        for artifact in artifacts
    }
    findings: list[dict[str, Any]] = []
    for module_id, artifacts in sorted(topology["consumed_artifacts"].items()):
        if _phase_id(module_id) == "P0":
            continue
        for artifact in sorted(artifacts.intersection(p0_artifacts)):
            findings.append(
                finding(
                    "P0_ECONOMIC_INPUT",
                    "P0",
                    module_id,
                    artifact,
                    "An artifact emitted by Phase 0 is consumed by an economic phase",
                )
            )
    return findings


def _deduplicate_findings(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in raw:
        key = (
            item["rule_id"],
            item["source_module"],
            item["target_module"],
            item["artifact"],
        )
        unique[key] = item
    return [
        {"finding_id": f"FC-{index:04d}", **unique[key]}
        for index, key in enumerate(sorted(unique), start=1)
    ]


def _build_report(
    *,
    findings: list[dict[str, Any]],
    validated: set[tuple[str, str]],
    declared: set[tuple[str, str]],
    validated_lineage: str,
    rules: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    explicit_or_p0 = {"EXPLICIT_FORBIDDEN_CONNECTION", "P0_ECONOMIC_INPUT"}
    matrix_rules = {
        "UNDECLARED_VALIDATED_EDGE",
        "VALIDATED_EDGE_MISSING",
        "IO_MATRIX_ASYMMETRY",
        "UNKNOWN_MODULE_REFERENCE",
    }
    no_forbidden = not any(item["rule_id"] in explicit_or_p0 for item in findings)
    phase0_safe = not any(item["rule_id"] == "P0_ECONOMIC_INPUT" for item in findings)
    matrix_consistent = not any(item["rule_id"] in matrix_rules for item in findings)
    normalized = {
        "validated_lineage": validated_lineage,
        "validated_edges": sorted(validated),
        "declared_edges": sorted(declared),
        "rules": rules,
        "findings": findings,
    }
    digest = stable_digest(normalized)
    blocking = bool(findings)
    return {
        "artifact_id": f"forbidden-connection-report-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "validated_connection_matrix_lineage_id": validated_lineage,
        "evaluated_connection_count": len(validated),
        "declared_connection_count": len(declared),
        "forbidden_connections": len(findings),
        "forbidden_connection_count": len(findings),
        "critical_finding_count": len(findings),
        "warning_finding_count": 0,
        "findings": findings,
        "status": "FAIL" if blocking else "PASS",
        "severity": "CRITICAL" if blocking else "NONE",
        "release_blocking": blocking,
        "no_forbidden_economic_connection": no_forbidden,
        "phase0_not_economic_input": phase0_safe,
        "connection_matrix_consistent": matrix_consistent,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_inputs(inputs, config, REQUIRED_INPUTS)
    leaked = find_forbidden_fields(inputs, forbidden_fields())
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    runtime_version = str(config.get("pipeline_version") or PIPELINE_VERSION)
    if normalized_version(runtime_version) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("pipeline version is incompatible")

    validated, lineage, scope_phase = validated_edges(inputs["validated_connection_matrix"])
    topology = build_global_topology(
        load_io_matrices(inputs["module_io_matrix_all_phases"], config.get("release_scope")),
        config.get("release_scope"),
    )
    emit_edges = topology["emit_edges"]
    consume_edges = topology["consume_edges"]
    declared = emit_edges.intersection(consume_edges)
    expected = _expected_validated_edges(validated, declared, scope_phase)
    rules = load_policy(inputs["forbidden_connection_matrix_yaml"])

    raw = _matrix_findings(topology=topology, validated=validated, expected=expected)
    raw.extend(_policy_findings(declared, rules))
    raw.extend(_p0_artifact_findings(topology))
    findings = _deduplicate_findings(raw)
    report = _build_report(
        findings=findings,
        validated=validated,
        declared=declared,
        validated_lineage=lineage,
        rules=rules,
        config=config,
    )
    validate_output(
        report,
        schema_name="forbidden_connection_report.schema.yaml",
        artifact_name=OUTPUT_NAME,
        forbidden_fields=forbidden_fields(),
    )
    return module_result(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        contract=CONTRACT,
        required_inputs=REQUIRED_INPUTS,
        output_name=OUTPUT_NAME,
        artifact=report,
    )
