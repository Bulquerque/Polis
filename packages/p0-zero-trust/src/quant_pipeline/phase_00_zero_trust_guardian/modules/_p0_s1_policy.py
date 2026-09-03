from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import canonical_phases
from ._p0_s1_common import (
    load_mapping_input,
    normalized_version,
    stable_digest,
    validate_lineage_id,
)


PHASE_PLANE = {item["phase_id"]: item["plane"] for item in canonical_phases()}


def validated_edges(value: Any) -> tuple[set[tuple[str, str]], str, str | None]:
    if isinstance(value, dict) and set(value) == {"source"}:
        raise ContractValidationError("validated_connection_matrix is a symbolic placeholder")
    artifact, _ = load_mapping_input(
        value,
        label="validated connection matrix",
        symbolic_name="validated_connection_matrix",
    )
    required = {"artifact_id", "pipeline_version", "lineage_id"}
    missing = sorted(required.difference(artifact))
    if missing:
        raise ContractValidationError(f"validated_connection_matrix missing fields: {missing}")
    if normalized_version(artifact["pipeline_version"]) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("validated_connection_matrix pipeline version is incompatible")
    lineage_id = validate_lineage_id(artifact.get("lineage_id"), "validated_connection_matrix")
    edge_values = next(
        (
            artifact[key]
            for key in ("connections", "edges", "validated_connections", "module_connections")
            if key in artifact
        ),
        None,
    )
    if not isinstance(edge_values, list) or not edge_values:
        raise ContractValidationError(
            "validated_connection_matrix must contain materialized connections"
        )
    edges = {_edge_from_mapping(item, "validated_connection_matrix") for item in edge_values}
    if len(edges) != len(edge_values):
        raise ContractValidationError("validated_connection_matrix contains duplicate connections")
    if artifact.get("connection_count") not in (None, len(edges)):
        raise ContractValidationError("validated_connection_matrix connection_count is inconsistent")
    if artifact.get("promotion_blocked") is not True:
        raise ContractValidationError("validated_connection_matrix must remain promotion_blocked")
    phase = artifact.get("phase")
    return edges, lineage_id, str(phase) if isinstance(phase, str) else None


def load_policy(value: Any) -> list[dict[str, Any]]:
    matrix, _ = load_mapping_input(
        value,
        label="forbidden connection matrix",
        symbolic_name="forbidden_connection_matrix_yaml",
    )
    structured = matrix.get("policy_rules")
    if isinstance(structured, list) and structured:
        return [_validate_rule(rule, index) for index, rule in enumerate(structured)]
    legacy = matrix.get("forbidden_connections")
    if not isinstance(legacy, list) or not legacy:
        raise ContractValidationError("forbidden_connection_matrix_yaml has no rules")
    return [_legacy_rule(rule, index) for index, rule in enumerate(legacy)]


def rule_matches(rule: dict[str, Any], edge: tuple[str, str]) -> bool:
    source, target = edge
    return _selector_matches(rule["source"], source) and _selector_matches(rule["target"], target)


def finding(
    rule_id: str,
    source: str,
    target: str,
    artifact: str,
    message: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "severity": "CRITICAL",
        "source_module": source,
        "target_module": target,
        "artifact": artifact,
        "message": message,
        "release_blocking": True,
    }


def stable_finding_fingerprint(finding_value: dict[str, Any]) -> str:
    identity = {
        "rule_id": finding_value["rule_id"],
        "source_module": finding_value["source_module"],
        "target_module": finding_value["target_module"],
        "artifact": finding_value["artifact"],
    }
    return f"sha256:{stable_digest(identity)}"


def _edge_from_mapping(value: Any, label: str) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ContractValidationError(f"{label} connection must be a mapping")
    source = next(
        (value[key] for key in ("source_module", "from_module", "source", "from") if key in value),
        None,
    )
    target = next(
        (value[key] for key in ("target_module", "to_module", "destination", "target", "to") if key in value),
        None,
    )
    if not isinstance(source, str) or not source.strip():
        raise ContractValidationError(f"{label} connection source is invalid")
    if not isinstance(target, str) or not target.strip():
        raise ContractValidationError(f"{label} connection target is invalid")
    return source.strip(), target.strip()


def _validate_rule(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractValidationError(f"invalid forbidden connection rule at index {index}")
    required = {"rule_id", "source", "target", "severity", "release_blocking", "message"}
    if not required.issubset(value):
        raise ContractValidationError(f"invalid forbidden connection rule at index {index}")
    if value["severity"] != "CRITICAL" or value["release_blocking"] is not True:
        raise ContractValidationError(f"invalid forbidden connection rule at index {index}")
    if not isinstance(value["source"], dict) or not isinstance(value["target"], dict):
        raise ContractValidationError(f"invalid forbidden connection rule at index {index}")
    return {
        "rule_id": str(value["rule_id"]),
        "source": dict(value["source"]),
        "target": dict(value["target"]),
        "severity": "CRITICAL",
        "release_blocking": True,
        "message": str(value["message"]),
    }


def _legacy_rule(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, str):
        source, target = _edge_from_mapping(value, "forbidden_connection_matrix_yaml")
        return _literal_rule(source, target)
    parts = value.split("->")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise ContractValidationError(f"invalid forbidden connection rule at index {index}")
    source, target = (part.strip() for part in parts)
    if source == "phase_00_zero_trust_guardian" and target == "economic_feature_flow":
        return {
            "rule_id": "EXPLICIT_FORBIDDEN_CONNECTION",
            "source": {"phase": "P0"},
            "target": {"plane": "economic_pipeline"},
            "severity": "CRITICAL",
            "release_blocking": True,
            "message": f"Connection matches forbidden rule {source}->{target}",
        }
    if source == "phase_00_zero_trust_guardian" and target == "trade_decision_flow":
        return {
            "rule_id": "EXPLICIT_FORBIDDEN_CONNECTION",
            "source": {"phase": "P0"},
            "target": {"phase": "P8"},
            "severity": "CRITICAL",
            "release_blocking": True,
            "message": f"Connection matches forbidden rule {source}->{target}",
        }
    return _literal_rule(source, target)


def _literal_rule(source: str, target: str) -> dict[str, Any]:
    return {
        "rule_id": "EXPLICIT_FORBIDDEN_CONNECTION",
        "source": {"module_or_phase": source},
        "target": {"module_or_phase": target},
        "severity": "CRITICAL",
        "release_blocking": True,
        "message": f"Connection matches forbidden rule {source}->{target}",
    }


def _selector_matches(selector: dict[str, Any], module_id: str) -> bool:
    phase = module_id.split(".", 1)[0]
    if selector.get("phase") is not None:
        return selector["phase"] == phase
    if selector.get("plane") is not None:
        return selector["plane"] == PHASE_PLANE.get(phase)
    literal = selector.get("module_or_phase")
    if literal is not None:
        return literal in {"*", module_id, phase}
    return False
