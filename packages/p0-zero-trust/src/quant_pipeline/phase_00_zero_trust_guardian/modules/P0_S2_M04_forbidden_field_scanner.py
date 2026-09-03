from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ._s2_common import created_at, load_yaml_mapping, normalized_version, stable_digest, validate_schema_value
from ._s2_forbidden_policy import (
    contains_placeholder,
    load_mapping_input,
    load_policy,
    scan_sources,
    source_digest,
)
from ._s2_forbidden_sources import artifact_sources, schema_sources


WORKSPACE_ROOT = Path(__file__).resolve().parents[6]


def _validate_artifact(artifact: dict[str, Any]) -> None:
    schema = load_yaml_mapping(
        SCHEMA_ROOT / "forbidden_field_report.schema.yaml",
        "forbidden field report schema",
    )
    validate_schema_value(artifact, schema, "forbidden_field_report")


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config, required_inputs = _validated_runtime(inputs, config)
    schema_registry, schema_source = load_mapping_input(
        inputs["schema_registry"],
        "schemas",
        "schema_registry",
        workspace_root=WORKSPACE_ROOT,
    )
    artifact_registry, artifact_source = load_mapping_input(
        inputs["artifact_registry"],
        "artifacts",
        "artifact_registry",
        workspace_root=WORKSPACE_ROOT,
    )
    policy = load_policy(inputs["forbidden_fields_yaml"], workspace_root=WORKSPACE_ROOT)
    schema_items = schema_sources(
        schema_registry,
        workspace_root=WORKSPACE_ROOT,
        allow_global=str(config.get("release_scope", "")).upper() == "P0_TECHNICAL_CLOSURE",
    )
    artifact_items = artifact_sources(artifact_registry, workspace_root=WORKSPACE_ROOT)
    artifact = _build_report(
        schema_registry,
        schema_source,
        artifact_source,
        schema_items,
        artifact_items,
        policy,
        config,
    )
    _validate_artifact(artifact)
    return {
        "module_id": "P0.S2.M04",
        "module_name": "forbidden_field_scanner",
        "phase": "P0",
        "subphase": "P0.S2",
        "contract": "P0_S2_M04_forbidden_field_scanner.yaml",
        "required_inputs": required_inputs,
        "outputs": {"forbidden_field_report": artifact},
    }


def _validated_runtime(
    inputs: dict, config: dict | None
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    required = ["schema_registry", "artifact_registry", "forbidden_fields_yaml"]
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    if contains_placeholder(inputs):
        raise ContractValidationError("symbolic placeholders are not accepted")
    runtime_version = str(config.get("pipeline_version") or PIPELINE_VERSION)
    if normalized_version(runtime_version) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("pipeline version is incompatible")
    return config, required


def _build_report(
    schema_registry: dict[str, Any],
    schema_source: str,
    artifact_source: str,
    schema_items: list[dict[str, Any]],
    artifact_items: list[dict[str, Any]],
    policy: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    sources = schema_items + artifact_items
    violations, occurrence_count, allowed_count = scan_sources(sources, policy)
    target_count = sum(item["code"] == "TARGET_IN_INFERENCE" for item in violations)
    rank_count = sum(item["code"] == "RANK_SCORE_BEFORE_P7" for item in violations)
    normalized = _normalized_scan_payload(
        schema_registry, schema_source, artifact_source, policy, sources, violations
    )
    digest = stable_digest(normalized)
    blocked = bool(violations)
    return {
        "artifact_id": f"forbidden-field-report-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "schema_registry_source": schema_source,
        "artifact_registry_source": artifact_source,
        "policy_source": policy.source_path,
        "schema_registry_lineage_id": normalized["schema_registry_lineage_id"],
        "policy_field_count": len(policy.all_fields),
        "scanned_schema_count": len(schema_items),
        "scanned_artifact_count": len(artifact_items),
        "scanned_document_count": len(sources),
        "field_occurrence_count": occurrence_count,
        "allowed_exception_count": allowed_count,
        "violation_count": len(violations),
        "target_inference_violation_count": target_count,
        "rank_score_pre_p7_violation_count": rank_count,
        "other_forbidden_violation_count": len(violations) - target_count - rank_count,
        "violations": violations,
        "status": "FAIL" if blocked else "PASS",
        "severity": "CRITICAL" if blocked else "NONE",
        "release_blocking": blocked,
        "target_not_in_inference": target_count == 0,
        "rank_score_not_before_phase7": rank_count == 0,
        "recursive_scan_complete": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def _normalized_scan_payload(
    schema_registry: dict[str, Any],
    schema_source: str,
    artifact_source: str,
    policy: Any,
    sources: list[dict[str, Any]],
    violations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_registry_source": schema_source,
        "artifact_registry_source": artifact_source,
        "policy_source": policy.source_path,
        "schema_registry_lineage_id": str(schema_registry.get("lineage_id") or "not_declared"),
        "policy_fields": sorted(policy.all_fields),
        "phase_policy_fields": {
            phase: sorted(fields) for phase, fields in sorted(policy.phase_forbidden.items())
        },
        "scanned_sources": [
            {
                "source_kind": source["source_kind"],
                "source_id": source["source_id"],
                "schema_id": source["schema_id"],
                "phases": source["phases"],
                "mode": source["mode"],
                "content_sha256": source_digest(source["document"]),
            }
            for source in sources
        ],
        "violations": violations,
    }
