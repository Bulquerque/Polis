from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import meta, no_forbidden_rows, records, require_inputs
from ._s1_core import compare_shared_fields, match_rows, rows_or_empty

_REQUIRED_INPUTS = [
    "handoff_manifest_to_phase_2",
    "source_registry",
    "raw_file_inventory",
    "source_snapshot_registry",
    "raw_readability_report",
    "raw_schema_hint_report",
    "ingestion_error_report",
]


def _blocking_findings(row: dict, *, inputs: dict) -> list[dict]:
    findings: list[dict] = []
    source_id = row.get("source_id")
    file_hash = row.get("file_hash")
    if not source_id:
        findings.append({"code": "P2_S1_M01_SOURCE_ID_MISSING", "severity": "BLOCK"})
    if not file_hash:
        findings.append({"code": "P2_S1_M01_FILE_HASH_MISSING", "severity": "BLOCK"})

    snapshots = match_rows(row, rows_or_empty(inputs["source_snapshot_registry"], "source_snapshot_registry"))
    for snapshot in snapshots:
        findings.extend(
            compare_shared_fields(
                row,
                snapshot,
                (
                    "source_id",
                    "ingestion_run_id",
                    "raw_artifact_id",
                    "raw_artifact_path",
                    "file_hash",
                    "file_size_bytes",
                    "declared_available_at",
                    "readability_status",
                    "pipeline_version",
                ),
                error_prefix="P2_S1_M01_SNAPSHOT",
            )
        )

    inventory = match_rows(row, rows_or_empty(inputs["raw_file_inventory"], "raw_file_inventory"))
    for inventory_row in inventory:
        findings.extend(
            compare_shared_fields(
                row,
                inventory_row,
                ("source_id", "raw_artifact_id", "raw_artifact_path", "file_hash", "file_size_bytes"),
                error_prefix="P2_S1_M01_INVENTORY",
            )
        )

    readability = match_rows(row, rows_or_empty(inputs["raw_readability_report"], "raw_readability_report"))
    for readability_row in readability:
        findings.extend(
            compare_shared_fields(
                row,
                readability_row,
                ("source_id", "raw_artifact_id", "readability_status"),
                error_prefix="P2_S1_M01_READABILITY",
            )
        )
    return findings


def _validate_declared_references(rows: list[dict], inputs: dict) -> list[dict]:
    findings: list[dict] = []
    source_registry = rows_or_empty(inputs["source_registry"], "source_registry")
    registry_source_ids = {str(row["source_id"]) for row in source_registry if row.get("source_id")}
    if registry_source_ids:
        for row in rows:
            if str(row.get("source_id")) not in registry_source_ids:
                findings.append(
                    {
                        "code": "P2_S1_M01_SOURCE_REGISTRY_REFERENCE_MISSING",
                        "severity": "BLOCK",
                        "source_id": row.get("source_id"),
                    }
                )

    schema_hints = rows_or_empty(inputs["raw_schema_hint_report"], "raw_schema_hint_report")
    exposed_hint_ids = {
        str(hint.get("schema_hint_id"))
        for hint in schema_hints
        if hint.get("schema_hint_id") not in (None, "")
    }
    # Enforce only when the report exposes schema_hint_id explicitly; its artifact_id
    # identifies the report itself and must not be confused with a hint identifier.
    if exposed_hint_ids:
        for row in rows:
            hint_id = row.get("schema_hint_id")
            if hint_id and str(hint_id) not in exposed_hint_ids:
                findings.append(
                    {
                        "code": "P2_S1_M01_SCHEMA_HINT_REFERENCE_MISSING",
                        "severity": "BLOCK",
                        "source_id": row.get("source_id"),
                        "schema_hint_id": hint_id,
                    }
                )
    return findings


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    require_inputs(inputs, _REQUIRED_INPUTS)

    handoff_rows = records(inputs["handoff_manifest_to_phase_2"], "handoff_manifest_to_phase_2")
    if not handoff_rows:
        raise ContractValidationError("all_phase1_outputs_present violation: handoff manifest is empty")
    no_forbidden_rows(handoff_rows)

    findings: list[dict] = []
    enriched_rows: list[dict] = []
    seen_artifacts: set[str] = set()

    for row in handoff_rows:
        artifact_identity = str(row.get("raw_artifact_id") or row.get("handoff_artifact_id") or "")
        if artifact_identity:
            if artifact_identity in seen_artifacts:
                findings.append(
                    {
                        "code": "P2_S1_M01_DUPLICATE_ARTIFACT_REFERENCE",
                        "severity": "BLOCK",
                        "artifact_id": artifact_identity,
                    }
                )
            seen_artifacts.add(artifact_identity)

        row_findings = _blocking_findings(row, inputs=inputs)
        findings.extend(row_findings)

        error_rows = match_rows(row, rows_or_empty(inputs["ingestion_error_report"], "ingestion_error_report"))
        source_errors = [dict(error_row) for error_row in error_rows if error_row.get("error_flag") or error_row.get("is_blocking")]
        enriched_rows.append({**row, "s1_validation_findings": row_findings, "ingestion_errors": source_errors})

    findings.extend(_validate_declared_references(handoff_rows, inputs))
    if config.get("strict_physical_validation"):
        # A declared artifact is not proven by an empty lookup.  Fail closed
        # before S1.M02 can read an unbound path or descriptor.
        for row in handoff_rows:
            identity = row.get("raw_artifact_id") or row.get("handoff_artifact_id")
            for label, key in (
                ("snapshot", "source_snapshot_registry"),
                ("inventory", "raw_file_inventory"),
                ("readability", "raw_readability_report"),
            ):
                count = len(match_rows(row, rows_or_empty(inputs[key], key)))
                if count == 0:
                    findings.append({
                        "code": f"P2_S1_M01_{label.upper()}_REFERENCE_MISSING",
                        "severity": "BLOCK",
                        "artifact_id": identity,
                    })
                elif count > 1:
                    findings.append({
                        "code": f"P2_S1_M01_{label.upper()}_REFERENCE_AMBIGUOUS",
                        "severity": "BLOCK",
                        "artifact_id": identity,
                        "match_count": count,
                    })
    blocking = [finding for finding in findings if finding.get("severity") == "BLOCK"]
    if blocking:
        hash_related = any("HASH" in str(finding.get("code", "")) for finding in blocking)
        if hash_related:
            raise ContractValidationError(f"hashes_match violation: {blocking}")
        raise ContractValidationError(f"all_phase1_outputs_present violation: {blocking}")

    snapshot_rows = rows_or_empty(inputs["source_snapshot_registry"], "source_snapshot_registry")
    snapshot_match_count = sum(1 for row in handoff_rows if match_rows(row, snapshot_rows))
    bundle = {
        **meta("validated-phase1-handoff-bundle", enriched_rows, config),
        "validated": True,
        "records": enriched_rows,
        "hashes_match": True,
        "all_phase1_outputs_present": True,
        "validation_status": "PASS" if not findings else "WARN",
        "validation_findings": findings,
        "artifact_count": len(enriched_rows),
        "snapshot_match_count": snapshot_match_count,
        "blocking_findings_count": 0,
        "warning_findings_count": len(findings),
    }
    return {
        "module_id": "P2.S1.M01",
        "module_name": "phase1_handoff_validator",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S1",
        "contract": "P2_S1_M01_phase1_handoff_validator.yaml",
        "required_inputs": _REQUIRED_INPUTS,
        "outputs": {"validated_phase1_handoff_bundle": bundle},
    }
