from __future__ import annotations

from collections import defaultdict
from typing import Any

from quant_pipeline.common.hashing import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .cross_section import neutralize_values, normalize_values
from .errors import P4S7Error
from .records import ExposureRecord, NormalizationPolicyRecord


def _iso_timestamp(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat().replace("+00:00", "Z")  # type: ignore[union-attr]
    return str(value).replace("+00:00", "Z")


def _prepare_inputs(
    transformed_artifact: ArtifactEnvelope,
    exposure_artifact: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
) -> tuple[
    dict[tuple[str, str, str], list[dict[str, Any]]],
    dict[tuple[str, str], NormalizationPolicyRecord],
    dict[tuple[str, str], ExposureRecord],
    dict[str, dict[str, Any]],
]:
    policies = [NormalizationPolicyRecord.model_validate(record) for record in policy_artifact.records]
    policy_map = {(item.feature_id, item.horizon_group): item for item in policies}
    exposure_items = [ExposureRecord.model_validate(record) for record in exposure_artifact.records]
    exposure_map = {
        (_iso_timestamp(item.decision_time), item.entity_id): item
        for item in exposure_items
    }
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    catalog: dict[str, dict[str, Any]] = {}
    for record in transformed_artifact.records:
        key = (record["decision_time"], record["feature_id"], record["horizon_group"])
        groups[key].append(record)
        catalog[f"{record['horizon_group']}|{record['feature_id']}"] = _catalog_entry(record)
    missing = sorted({(key[1], key[2]) for key in groups} - set(policy_map))
    if missing:
        raise P4S7Error("P4_S7_M02_INPUT_INVALID", f"missing normalization policies: {missing}")
    return groups, policy_map, exposure_map, catalog


def _catalog_entry(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": record["feature_id"],
        "horizon_group": record["horizon_group"],
        "family_id": record["family_id"],
        "perspective_id": record["perspective_id"],
        "parameterization_id": record["parameterization_id"],
        "implementation_tier": record["implementation_tier"],
        "is_primary_parameterization": record["is_primary_parameterization"],
        "compute_cost": record["compute_cost"],
        "lineage_id": record["lineage_id"],
        "source_modalities": record["source_modalities"],
    }


def _empty_matrix_row(decision_time: str, entity: str, horizon: str) -> dict[str, Any]:
    return {
        "decision_time": decision_time,
        "entity_id": entity,
        "horizon_group": horizon,
        "available_at": None,
        "values": {},
        "raw_values": {},
        "transformed_values": {},
        "normalized_values": {},
        "neutralized_values": {},
        "missingness_mask": {},
        "feature_state_ids": {},
        "quality_state": "VALIDATED",
        "lineage_id": "",
    }


def _exposure_values(
    decision_time: object,
    entities: list[str],
    exposure_map: dict[tuple[str, str], ExposureRecord],
) -> dict[str, dict[str, float | None]]:
    canonical_time = _iso_timestamp(decision_time)
    return {
        entity: exposure_map[(canonical_time, entity)].values
        for entity in entities
        if (canonical_time, entity) in exposure_map
    }


def _process_snapshot(
    key: tuple[str, str, str],
    records: list[dict[str, Any]],
    policy: NormalizationPolicyRecord,
    exposure_map: dict[tuple[str, str], ExposureRecord],
) -> tuple[dict[str, Any], dict[str, float], dict[str, float], dict[str, float]]:
    decision_time, feature_id, horizon = key
    transformed = {
        record["entity_id"]: float(record["transformed_value"])
        for record in records
        if record["transformed_value"] is not None
    }
    normalized, center, scale, norm_quality = normalize_values(
        transformed, policy.normalization_type, policy.epsilon
    )
    exposure_values = _exposure_values(
        records[0]["decision_time"], list(transformed), exposure_map
    )
    neutralized, coefficients, entity_count, rank, neutral_quality = {}, {}, 0, None, "NOT_REQUESTED"
    if policy.neutralize_exposures:
        neutralized, coefficients, entity_count, rank, neutral_quality = neutralize_values(
            normalized,
            exposure_values,
            policy.neutralize_exposures,
            policy.ridge_alpha,
            policy.min_entities,
        )
    state_id = "norm:" + canonical_sha256(
        {"key": key, "center": center, "scale": scale, "coefficients": coefficients}
    )[:20]
    state = {
        "state_id": state_id,
        "decision_time": decision_time,
        "feature_id": feature_id,
        "horizon_group": horizon,
        "normalization_type": policy.normalization_type,
        "center": center,
        "scale": scale,
        "exposures": list(policy.neutralize_exposures),
        "coefficients": coefficients,
        "entity_count": entity_count,
        "rank": rank,
        "quality_state": f"{norm_quality}|{neutral_quality}",
    }
    return state, transformed, normalized, neutralized


def _apply_snapshot(
    rows: dict[tuple[str, str, str], dict[str, Any]],
    key: tuple[str, str, str],
    records: list[dict[str, Any]],
    policy: NormalizationPolicyRecord,
    state_id: str,
    normalized: dict[str, float],
    neutralized: dict[str, float],
) -> None:
    decision_time, feature_id, horizon = key
    for record in records:
        entity = record["entity_id"]
        available_at = str(record.get("available_at", "")).strip()
        if not available_at:
            raise P4S7Error(
                "P4_S7_M02_AVAILABILITY_MISSING",
                f"feature record {feature_id} has no explicit available_at",
            )
        row = rows.setdefault(
            (decision_time, entity, horizon),
            _empty_matrix_row(decision_time, entity, horizon),
        )
        if row["available_at"] is None or available_at > str(row["available_at"]):
            row["available_at"] = available_at
        values = {
            "raw": record["raw_value"],
            "transformed": record["transformed_value"],
            "normalized": normalized.get(entity),
            "neutralized": neutralized.get(entity),
        }
        final_value = values[policy.final_view]
        _store_feature_views(
            row,
            feature_id,
            values,
            final_value,
            state_id,
            record["lineage_id"],
        )
        if final_value is None:
            row["quality_state"] = "DEGRADED"
        row["values"][feature_id] = final_value


def _store_feature_views(
    row: dict[str, Any],
    feature_id: str,
    views: dict[str, float | None],
    final_value: float | None,
    state_id: str,
    lineage_id: str,
) -> None:
    row["raw_values"][feature_id] = views["raw"]
    row["transformed_values"][feature_id] = views["transformed"]
    row["normalized_values"][feature_id] = views["normalized"]
    row["neutralized_values"][feature_id] = views["neutralized"]
    row["missingness_mask"][feature_id] = final_value is None
    row["feature_state_ids"][feature_id] = state_id
    row["lineage_id"] = canonical_sha256([row["lineage_id"], lineage_id, state_id])


def _build_outputs(
    rows: dict[tuple[str, str, str], dict[str, Any]],
    state_records: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    artifacts: tuple[ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope],
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    transformed, exposure, policy = artifacts
    lineage = canonical_sha256(
        [transformed.lineage_id, exposure.lineage_id, policy.lineage_id, "P4.S7.M02"]
    )
    matrix = build_artifact(
        artifact_name="underlying_feature_matrix_interpretable",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M02",
        context=context,
        grain=("decision_time", "entity_id", "horizon_group"),
        records=[rows[key] for key in sorted(rows)],
        lineage_id=lineage,
        metadata={"feature_catalog": catalog, "source_artifact": transformed.artifact_id},
    )
    raw_records = []
    for row in (rows[key] for key in sorted(rows)):
        raw_row = dict(row)
        raw_row["values"] = dict(row["raw_values"])
        raw_row["quality_state"] = "VALIDATED" if all(
            value is not None for value in raw_row["values"].values()
        ) else "DEGRADED"
        raw_records.append(raw_row)
    raw_matrix = build_artifact(
        artifact_name="underlying_feature_matrix_raw",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M02",
        context=context,
        grain=("decision_time", "entity_id", "horizon_group"),
        records=raw_records,
        lineage_id=canonical_sha256([lineage, "raw_view"]),
        metadata={
            "feature_catalog": catalog,
            "source_artifact": transformed.artifact_id,
            "view_semantics": "raw_transformed_inputs_before_normalization",
            "paired_interpretable_artifact_id": matrix.artifact_id,
        },
    )
    states = build_artifact(
        artifact_name="normalization_neutralization_fit_state_manifest",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S7.M02",
        context=context,
        grain=("state_id",),
        records=state_records,
        lineage_id=lineage,
        metadata={"matrix_id": matrix.artifact_id},
    )
    return {matrix.artifact_name: matrix, raw_matrix.artifact_name: raw_matrix, states.artifact_name: states}


def build_normalized_matrix(
    transformed_artifact: ArtifactEnvelope,
    exposure_artifact: ArtifactEnvelope,
    policy_artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    groups, policies, exposure_map, catalog = _prepare_inputs(
        transformed_artifact, exposure_artifact, policy_artifact
    )
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    state_records: list[dict[str, Any]] = []
    for key in sorted(groups):
        state, _, normalized, neutralized = _process_snapshot(
            key, groups[key], policies[(key[1], key[2])], exposure_map
        )
        state_records.append(state)
        _apply_snapshot(
            rows,
            key,
            groups[key],
            policies[(key[1], key[2])],
            state["state_id"],
            normalized,
            neutralized,
        )
    return _build_outputs(
        rows,
        state_records,
        catalog,
        (transformed_artifact, exposure_artifact, policy_artifact),
        context,
    )
