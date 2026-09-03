"""Fail-closed validation for the P4 V14.9 handoff surface."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..errors import ContractError
from .models import (
    P4ArtifactEnvelope,
    P4BoundaryCatalog,
    P4GateState,
    P5_PHASE,
    _utc,
)

_REQUIRED_HANDOFF = {
    "underlying_feature_matrix_raw",
    "underlying_feature_matrix_selected",
    "underlying_feature_factors_pca",
    "underlying_feature_embeddings",
    "feature_selection_report",
    "feature_lineage_report",
    "drift_safety_report",
}
_ALLOWED_VIEWS = {
    "TABULAR_INTERPRETABLE",
    "CROSS_SECTIONAL_RANKED",
    "SEQUENCE_MULTI_HORIZON",
    "LATENT_FAMILY",
    "SPARSE_MODALITY_AWARE",
}
_EXPECTED_GRAIN = {
    "TABULAR_INTERPRETABLE": {"decision_time", "entity_id", "horizon_group"},
    "CROSS_SECTIONAL_RANKED": {"decision_time", "entity_id", "horizon_group"},
    "SEQUENCE_MULTI_HORIZON": {"decision_time", "entity_id", "horizon_group"},
    "LATENT_FAMILY": {"decision_time", "entity_id", "family_id", "horizon_group"},
    "SPARSE_MODALITY_AWARE": {"decision_time", "entity_id", "horizon_group"},
}


def build_boundary_catalog(
    *,
    handoff: dict[str, Any],
    view_manifest: dict[str, Any],
    view_bundle: dict[str, Any],
    quality_gate: dict[str, Any],
    artifact_catalog: dict[str, Any],
    expected_cycle_id: str,
    p5_as_of_time: datetime,
    p5_generated_at: datetime,
    expected_run_id: str | None = None,
) -> P4BoundaryCatalog:
    parsed_handoff = _parse_named(handoff, "phase5_feature_handoff_manifest")
    parsed_manifest = _parse_named(view_manifest, "model_consumer_view_manifest")
    parsed_bundle = _parse_named(view_bundle, "model_consumer_view_bundle")
    parsed_gate = _parse_named(quality_gate, "p4_quality_gate_decision")
    _same_run(parsed_handoff, parsed_manifest, parsed_bundle, parsed_gate)
    _validate_clocks(parsed_handoff, parsed_manifest, parsed_bundle, parsed_gate,
                     expected_cycle_id, p5_as_of_time, p5_generated_at, expected_run_id)
    catalog = _parse_catalog(artifact_catalog, parsed_handoff)
    _validate_handoff_records(parsed_handoff, catalog)
    _validate_view_contract(parsed_handoff, parsed_manifest, parsed_bundle, catalog)
    gate_state = _gate_state(parsed_handoff, parsed_manifest, parsed_gate)
    if gate_state.blocking:
        raise ContractError("P4 V14.9 handoff is blocked")
    return P4BoundaryCatalog(
        handoff=parsed_handoff,
        view_manifest=parsed_manifest,
        view_bundle=parsed_bundle,
        quality_gate=parsed_gate,
        artifacts=catalog,
        gate_state=gate_state,
    )


def _parse_named(value: dict[str, Any], expected_name: str) -> P4ArtifactEnvelope:
    try:
        artifact = P4ArtifactEnvelope.model_validate(value)
    except ValueError as exc:
        raise ContractError(f"invalid P4 artifact {expected_name}: {exc}") from exc
    if artifact.artifact_name != expected_name:
        raise ContractError(f"expected P4 artifact {expected_name}, got {artifact.artifact_name}")
    return artifact


def _parse_catalog(
    raw: dict[str, Any], handoff: P4ArtifactEnvelope,
) -> dict[str, P4ArtifactEnvelope]:
    if not isinstance(raw, dict) or not raw:
        raise ContractError("p4_artifact_catalog must be a non-empty mapping")
    parsed: dict[str, P4ArtifactEnvelope] = {}
    ids: set[str] = set()
    for supplied_name, value in raw.items():
        if not isinstance(value, dict):
            raise ContractError(f"P4 catalog entry {supplied_name} must be an object")
        try:
            artifact = P4ArtifactEnvelope.model_validate(value)
        except ValueError as exc:
            raise ContractError(f"invalid P4 catalog entry {supplied_name}: {exc}") from exc
        if supplied_name != artifact.artifact_name:
            raise ContractError(f"P4 catalog key/name mismatch: {supplied_name}")
        if artifact.artifact_id in ids:
            raise ContractError(f"duplicate P4 artifact_id: {artifact.artifact_id}")
        if (artifact.run_id, artifact.cycle_id, artifact.as_of_time) != (
            handoff.run_id, handoff.cycle_id, handoff.as_of_time,
        ):
            raise ContractError(f"P4 catalog identity differs for {supplied_name}")
        ids.add(artifact.artifact_id)
        parsed[supplied_name] = artifact
    return parsed


def _same_run(*artifacts: P4ArtifactEnvelope) -> None:
    identities = {(item.run_id, item.cycle_id, item.as_of_time) for item in artifacts}
    if len(identities) != 1:
        raise ContractError("P4 boundary artifacts do not share run/cycle/as_of identity")


def _validate_clocks(
    handoff: P4ArtifactEnvelope,
    manifest: P4ArtifactEnvelope,
    bundle: P4ArtifactEnvelope,
    gate: P4ArtifactEnvelope,
    expected_cycle_id: str,
    p5_as_of_time: datetime,
    p5_generated_at: datetime,
    expected_run_id: str | None = None,
) -> None:
    if expected_run_id is not None and handoff.run_id != expected_run_id:
        raise ContractError("P4 handoff run_id differs from P5 run_id")
    if handoff.cycle_id != expected_cycle_id:
        raise ContractError("P4 handoff cycle_id differs from P5 cycle_id")
    if handoff.as_of_time > _utc(p5_as_of_time):
        raise ContractError("P4 as_of_time exceeds P5 as_of_time")
    if handoff.created_at > _utc(p5_generated_at):
        raise ContractError("P4 created_at exceeds P5 generated_at")
    if any(item.created_at > handoff.created_at for item in (manifest, bundle, gate)):
        raise ContractError("P4 boundary artifact created_at exceeds handoff created_at")
    if handoff.metadata.get("destination_phase") != P5_PHASE:
        raise ContractError("P4 handoff destination_phase is not P5")


def _validate_handoff_records(
    handoff: P4ArtifactEnvelope,
    catalog: dict[str, P4ArtifactEnvelope],
) -> None:
    rows = {str(row.get("artifact_name")): row for row in handoff.records}
    if len(rows) != len(handoff.records):
        raise ContractError("P4 handoff artifact_name values must be unique")
    missing = sorted(_REQUIRED_HANDOFF - set(rows))
    if missing:
        raise ContractError(f"P4 handoff lacks required artifacts: {missing}")
    for name, row in rows.items():
        artifact = catalog.get(name)
        if artifact is None:
            raise ContractError(f"P4 handoff reference is absent from artifact catalog: {name}")
        checks = {
            "artifact_id": artifact.artifact_id,
            "content_hash": artifact.content_hash,
            "schema_version": artifact.schema_version,
            "record_count": artifact.record_count,
            "grain": list(artifact.grain),
            "execution_status": artifact.execution_status.value,
            "quality_status": artifact.quality_status.value,
        }
        for field, expected in checks.items():
            if row.get(field) != expected:
                raise ContractError(f"P4 handoff {name}.{field} differs from catalog")


def _validate_view_contract(
    handoff: P4ArtifactEnvelope,
    manifest: P4ArtifactEnvelope,
    bundle: P4ArtifactEnvelope,
    catalog: dict[str, P4ArtifactEnvelope],
) -> None:
    if manifest.metadata.get("contains_predictions") is not False:
        raise ContractError("P4 consumer views must not contain predictions")
    if bundle.metadata.get("contains_payload_copies") is not False:
        raise ContractError("P4 consumer-view bundle must contain references only")
    if handoff.metadata.get("consumer_view_manifest_id") != manifest.artifact_id:
        raise ContractError("P4 handoff references a different consumer-view manifest")
    if handoff.metadata.get("consumer_view_manifest_hash") != manifest.content_hash:
        raise ContractError("P4 handoff consumer-view manifest hash mismatch")
    manifest_rows = _unique_rows(manifest.records, "view_id", "P4 view manifest")
    bundle_rows = _unique_rows(bundle.records, "view_id", "P4 view bundle")
    if not manifest_rows or set(manifest_rows) != set(bundle_rows):
        raise ContractError("P4 consumer-view manifest and bundle differ")
    unknown = sorted(set(manifest_rows) - _ALLOWED_VIEWS)
    if unknown:
        raise ContractError(f"unsupported P4 V14.9 consumer views: {unknown}")
    for view_id, declaration in manifest_rows.items():
        _validate_view_declaration(view_id, declaration)
        _validate_view_references(view_id, declaration, bundle_rows[view_id], catalog)


def _validate_view_declaration(view_id: str, row: dict[str, Any]) -> None:
    status = row.get("execution_status")
    if status not in {"PRODUCED", "UNAVAILABLE_UPSTREAM"}:
        raise ContractError(f"P4 view {view_id} has unsupported execution_status")
    if row.get("materialized") is not False:
        raise ContractError(f"P4 view {view_id} must be reference-only")
    if set(row.get("grain", [])) != _EXPECTED_GRAIN[view_id]:
        raise ContractError(f"P4 view {view_id} has incompatible grain")
    if not isinstance(row.get("artifact_ids"), list):
        raise ContractError(f"P4 view {view_id} artifact_ids must be an array")


def _validate_view_references(
    view_id: str,
    declaration: dict[str, Any],
    bundle_row: dict[str, Any],
    catalog: dict[str, P4ArtifactEnvelope],
) -> None:
    if bundle_row.get("payload_copied") is not False:
        raise ContractError(f"P4 view {view_id} unexpectedly copied payloads")
    if bundle_row.get("execution_status") != declaration.get("execution_status"):
        raise ContractError(f"P4 view {view_id} status differs between manifest and bundle")
    references = bundle_row.get("artifact_references", [])
    if not isinstance(references, list):
        raise ContractError(f"P4 view {view_id} artifact_references must be an array")
    if declaration.get("execution_status") == "UNAVAILABLE_UPSTREAM":
        if references or declaration.get("artifact_ids"):
            raise ContractError(f"unavailable P4 view {view_id} cannot reference artifacts")
        return
    declared_ids = set(map(str, declaration.get("artifact_ids", [])))
    referenced_ids: set[str] = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise ContractError(f"P4 view {view_id} reference must be an object")
        name = str(reference.get("artifact_name", ""))
        artifact = catalog.get(name)
        if artifact is None:
            raise ContractError(f"P4 view {view_id} references absent artifact {name}")
        expected = {
            "artifact_id": artifact.artifact_id,
            "content_hash": artifact.content_hash,
            "record_count": artifact.record_count,
            "execution_status": artifact.execution_status.value,
        }
        for field, value in expected.items():
            if reference.get(field) != value:
                raise ContractError(f"P4 view {view_id} reference {name}.{field} mismatch")
        referenced_ids.add(artifact.artifact_id)
    if referenced_ids != declared_ids:
        raise ContractError(f"P4 view {view_id} manifest/reference IDs differ")


def _gate_state(
    handoff: P4ArtifactEnvelope,
    manifest: P4ArtifactEnvelope,
    gate: P4ArtifactEnvelope,
) -> P4GateState:
    rows = [row for row in gate.records if row.get("gate_scope") == "HANDOFF"]
    if len(rows) != 1:
        raise ContractError("P4 quality gate requires exactly one HANDOFF decision")
    decision = str(rows[0].get("decision"))
    if handoff.metadata.get("gate_decision") != decision:
        raise ContractError("P4 handoff gate_decision differs from quality gate")
    blocked = tuple(sorted(
        str(row.get("scope_id")) for row in gate.records
        if row.get("gate_scope") == "FAMILY" and row.get("decision") == "BLOCK_FAMILY"
    ))
    declared_blocked = tuple(sorted(map(str, manifest.metadata.get("blocked_families", []))))
    if blocked != declared_blocked:
        raise ContractError("P4 blocked-family metadata differs from quality gate")
    degraded = tuple(sorted(
        str(row.get("scope_id")) for row in gate.records
        if row.get("gate_scope") == "FAMILY" and int(row.get("warn_count", 0)) > 0
    ))
    return P4GateState(
        handoff_decision=decision,
        completeness_status=str(handoff.metadata.get("completeness_status", "UNKNOWN")),
        blocked_families=blocked,
        degraded_families=degraded,
        execution_status=handoff.execution_status,
        quality_status=handoff.quality_status,
    )


def _unique_rows(rows: tuple[dict[str, Any], ...], key: str, label: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = str(row.get(key, "")).strip()
        if not identifier or identifier in output:
            raise ContractError(f"{label} requires unique non-empty {key}")
        output[identifier] = row
    return output
