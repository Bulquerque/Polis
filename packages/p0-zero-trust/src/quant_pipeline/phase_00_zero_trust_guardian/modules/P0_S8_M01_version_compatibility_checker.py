from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s8_utils import (
    artifact,
    created_at,
    digest,
    envelope,
    is_blocking,
    promotion_allowed,
    reject_forbidden,
    source_record,
)
from ._s8_release_inventory import build_release_inventory, compare_release_inventory
from ._s8_version_model import compare_versions, parse_version

_REQUIRED = [
    "validated_phase_registry",
    "contract_registry",
    "schema_registry",
    "release_manifest_previous",
]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    _validate_inputs(inputs)
    reject_forbidden(inputs)
    current, sources = _load_current_sources(inputs)
    previous, previous_source, previous_hash = artifact(
        inputs["release_manifest_previous"],
        "release_manifest_previous",
        require_current_version=False,
    )
    sources.append(source_record("release_manifest_previous", previous, previous_source, previous_hash))
    findings, warnings, version_status = _evaluate_versions(previous)
    findings.extend(_upstream_findings(current, previous))
    inventory = build_release_inventory(*current)
    previous_inventory = previous.get("compatibility_baseline")
    inventory_summary, inventory_findings, inventory_warnings = compare_release_inventory(previous_inventory, inventory)
    findings.extend(inventory_findings)
    warnings.extend(inventory_warnings)
    report = _build_report(config, previous, sources, inventory, inventory_summary, findings, warnings, version_status)
    return envelope(
        "P0.S8.M01",
        "version_compatibility_checker",
        "P0_S8_M01_version_compatibility_checker.yaml",
        _REQUIRED,
        "version_compatibility_report",
        report,
    )


def _validate_inputs(inputs: Any) -> None:
    if not isinstance(inputs, dict) or any(key not in inputs for key in _REQUIRED):
        raise ContractValidationError("missing required P0.S8.M01 inputs")


def _load_current_sources(inputs: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for label in _REQUIRED[:3]:
        data, source, source_hash = artifact(inputs[label], label)
        current.append(data)
        sources.append(source_record(label, data, source, source_hash))
    return current, sources


def _evaluate_versions(previous: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    previous_version = parse_version(previous["pipeline_version"], label="previous pipeline version")
    current_version = parse_version(PIPELINE_VERSION, label="current pipeline version")
    status, blocking = compare_versions(previous_version, current_version)
    findings: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if status == "INCOMPATIBLE_RELEASE_LINE":
        findings.append(_finding("incompatible_release_line", "previous release is on a different major/minor line"))
    elif status == "VERSION_DOWNGRADE":
        findings.append(_finding("version_downgrade", "candidate release is older than previous release"))
    elif status == "COMPATIBLE_FORWARD_REVISION":
        warnings.append(_finding("COMPATIBLE_FORWARD_REVISION", "candidate advances within the same release line", False))
    return findings, warnings, status


def _upstream_findings(current: list[dict[str, Any]], previous: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    labels = _REQUIRED[:3]
    for label, data in zip(labels, current):
        if is_blocking(data):
            findings.append(_finding("UPSTREAM_BLOCKING", f"{label} blocks release compatibility", artifact=label))
    if is_blocking(previous):
        findings.append(_finding("PREVIOUS_RELEASE_BLOCKING", "previous release manifest is blocking", artifact=_REQUIRED[3]))
    return findings


def _build_report(
    config: dict[str, Any],
    previous: dict[str, Any],
    sources: list[dict[str, Any]],
    inventory: dict[str, Any],
    inventory_summary: dict[str, Any],
    findings: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    version_status: str,
) -> dict[str, Any]:
    body = {
        "current_pipeline_version": PIPELINE_VERSION,
        "previous_pipeline_version": previous["pipeline_version"],
        "version_transition_status": version_status,
        "sources": sources,
        "current_inventory": inventory,
        "inventory_change_summary": inventory_summary,
        "findings": findings,
        "warnings": warnings,
    }
    checksum = digest(body)
    blocking = bool(findings)
    return {
        "artifact_id": f"version-compatibility-report-{checksum[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{checksum}",
        **body,
        "source_count": len(sources),
        "finding_count": len(findings),
        "warning_count": len(warnings),
        "schema_version_compatible": not any(_is_schema_blocker(item) for item in findings),
        "contract_version_compatible": not any(_is_contract_blocker(item) for item in findings),
        "pipeline_version_consistent": version_status not in {"INCOMPATIBLE_RELEASE_LINE", "VERSION_DOWNGRADE"},
        "status": "FAIL" if blocking else "PASS",
        "release_blocking": blocking,
        "production_promotion_allowed": promotion_allowed(config),
        "promotion_blocked": not promotion_allowed(config),
    }


def _finding(code: str, detail: str, blocking: bool = True, artifact: str = "release_manifest_previous") -> dict[str, Any]:
    return {
        "code": code,
        "artifact": artifact,
        "detail": detail,
        "severity": "BLOCKING" if blocking else "WARNING",
        "release_blocking": blocking,
    }


def _is_schema_blocker(item: dict[str, Any]) -> bool:
    return str(item.get("code", "")).startswith("SCHEMA_") and item.get("release_blocking") is True


def _is_contract_blocker(item: dict[str, Any]) -> bool:
    return str(item.get("code", "")).startswith("CONTRACT_") and item.get("release_blocking") is True
