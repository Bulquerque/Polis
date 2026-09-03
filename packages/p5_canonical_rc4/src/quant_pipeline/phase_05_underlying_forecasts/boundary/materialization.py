"""Projection of locked P4 V14.9 views into the stable, filtered P5 domain."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..errors import ContractError, DataQualityError, ReasonCode
from .filters import apply_filters, view_filter_report
from .models import P4ArtifactEnvelope, P4BoundaryCatalog, P4_VERSION, canonical_sha256



def materialize_consumer_views(
    catalog: P4BoundaryCatalog,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    declarations = {str(row["view_id"]): row for row in catalog.view_manifest.records}
    references = {str(row["view_id"]): row for row in catalog.view_bundle.records}
    views: list[dict[str, Any]] = []
    compatibility: list[dict[str, Any]] = []
    for view_id in sorted(declarations):
        declaration = declarations[view_id]
        status = str(references[view_id]["execution_status"])
        if status == "UNAVAILABLE_UPSTREAM":
            compatibility.append(_compatibility_row(view_id, declaration, status, 0, False))
            continue
        view = _materialize_view(view_id, declaration, catalog.artifacts)
        views.append(view)
        compatibility.append(
            _compatibility_row(view_id, declaration, status, len(view["records"]), True)
        )
    return views, compatibility


def _compatibility_row(
    view_id: str, declaration: dict[str, Any], status: str, count: int, authorized: bool,
) -> dict[str, Any]:
    return {
        "view_id": view_id,
        "authorized": authorized,
        "execution_status": status,
        "record_count": count,
        "grain": list(declaration.get("grain", [])),
        "missingness_policy": declaration.get("missingness_policy"),
        "limitations": list(declaration.get("limitations", [])),
    }


def _materialize_view(
    view_id: str,
    declaration: dict[str, Any],
    artifacts: dict[str, P4ArtifactEnvelope],
) -> dict[str, Any]:
    filters = tuple(str(item) for item in declaration.get("feature_filters", []))
    if view_id == "LATENT_FAMILY":
        records = _latent_records(artifacts)
    else:
        matrix = artifacts["underlying_feature_matrix_selected"]
        field = "normalized_values" if view_id == "CROSS_SECTIONAL_RANKED" else "values"
        records = _matrix_records(matrix, value_field=field, view_id=view_id, filters=filters)
    if not records:
        raise DataQualityError(f"P4 view {view_id} materialized no usable records")
    report = view_filter_report(view_id, filters, records)
    degraded = any(row["quality_state"] != "PASS" for row in records)
    limitations = list(declaration.get("limitations", []))
    if view_id == "LATENT_FAMILY" and not artifacts["underlying_feature_embeddings"].record_count:
        limitations.append("encoder unavailable; PCA-only latent representation")
        degraded = True
    return {
        "view_id": view_id,
        "view_type": view_id,
        "grain": ["underlying", "decision_time", "horizon_group"],
        "records": records,
        "missingness_policy": _missingness(declaration.get("missingness_policy")),
        "lineage_id": canonical_sha256({
            "view_id": view_id,
            "source_ids": declaration.get("artifact_ids", []),
            "filter_report": report,
        }),
        "quality_state": "PASS_WITH_LIMITATIONS" if degraded else "PASS",
        "limitations": sorted(set(limitations)),
        "source_artifact_ids": list(declaration.get("artifact_ids", [])),
        "p4_schema_version": P4_VERSION,
        "horizon_preserved": True,
        **report,
    }


def _matrix_records(
    artifact: P4ArtifactEnvelope, *, value_field: str, view_id: str, filters: tuple[str, ...],
) -> list[dict[str, Any]]:
    catalog = artifact.metadata.get("feature_catalog", {})
    if not isinstance(catalog, dict):
        raise DataQualityError("P4 selected matrix feature_catalog must be an object")
    output = []
    for row in artifact.records:
        record = _matrix_record(row, catalog, value_field, view_id, filters)
        if record is not None:
            output.append(record)
    return output


def _matrix_record(
    row: dict[str, Any],
    catalog: dict[str, Any],
    value_field: str,
    view_id: str,
    filters: tuple[str, ...],
) -> dict[str, Any] | None:
    values = row.get(value_field)
    if not isinstance(values, dict):
        raise DataQualityError(f"P4 selected matrix record lacks {value_field}")
    identity = _matrix_identity(row)
    _require_row_availability(row, view_id)
    raw = {str(name): value for name, value in values.items()}
    metadata = _feature_metadata(catalog, identity[2], raw)
    features, matched = apply_filters(raw, metadata, filters, row, view_id)
    if not features:
        return None
    filtered_metadata = {name: metadata[name] for name in features}
    modalities = sorted({
        modality for item in filtered_metadata.values()
        for modality in item.get("source_modalities", [])
    })
    record = _base_matrix_record(row, identity, features, filtered_metadata, modalities)
    record.update({
        "included_feature_ids": sorted(features),
        "excluded_feature_ids": sorted(set(raw) - set(features)),
        "matched_filters": sorted(matched),
    })
    if view_id == "SEQUENCE_MULTI_HORIZON":
        record["sequence_order_key"] = identity[0]
    if view_id == "SPARSE_MODALITY_AWARE":
        declared = sorted({
            modality for item in catalog.values() if isinstance(item, dict)
            for modality in item.get("source_modalities", [])
        })
        record["modality_mask"] = {name: name in modalities for name in declared}
    return record


def _matrix_identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    identity = (
        str(row.get("decision_time", "")), str(row.get("entity_id", "")),
        str(row.get("horizon_group", "")), str(row.get("lineage_id", "")),
    )
    if not all(identity):
        raise DataQualityError("P4 selected matrix row lacks identity/grain/lineage")
    return identity


def _require_row_availability(row: dict[str, Any], view_id: str) -> None:
    if not str(row.get("available_at", "")).strip():
        raise DataQualityError(
            f"P4 view {view_id} row lacks explicit available_at",
            reason_code=ReasonCode.FUTURE_INFORMATION,
        )


def _base_matrix_record(row, identity, features, metadata, modalities):
    decision_time, underlying, horizon_group, lineage_id = identity
    missingness = {
        name: bool(row.get("missingness_mask", {}).get(name, value is None))
        for name, value in features.items()
    }
    return {
        "underlying": underlying,
        "decision_time": decision_time,
        "as_of_time": decision_time,
        "available_at": str(row["available_at"]),
        "availability_source": "P4_ROW_EXPLICIT",
        "horizon_group": horizon_group,
        "features": features,
        "missingness_mask": missingness,
        "feature_state_ids": dict(row.get("feature_state_ids", {})),
        "feature_metadata": metadata,
        "source_modalities": modalities,
        "quality_state": str(row.get("quality_state", "PASS")),
        "lineage_id": lineage_id,
    }


def _feature_metadata(
    catalog: dict[str, Any], horizon_group: str, features: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for feature_id in features:
        metadata = catalog.get(f"{horizon_group}|{feature_id}")
        if not isinstance(metadata, dict):
            raise DataQualityError(f"P4 feature metadata is unavailable for {feature_id}")
        output[feature_id] = {
            "feature_id": feature_id,
            "family_id": metadata.get("family_id"),
            "source_modalities": list(metadata.get("source_modalities", [])),
            "parameterization_id": metadata.get("parameterization_id"),
            "implementation_tier": metadata.get("implementation_tier"),
            "lineage_id": metadata.get("lineage_id"),
        }
    return output


def _latent_records(artifacts: dict[str, P4ArtifactEnvelope]) -> list[dict[str, Any]]:
    sources = [artifacts["underlying_feature_factors_pca"]]
    embedding = artifacts["underlying_feature_embeddings"]
    if embedding.record_count:
        sources.append(embedding)
    grouped: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(dict)
    lineage: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    states: dict[tuple[str, str, str], dict[str, str]] = defaultdict(dict)
    availability: dict[tuple[str, str, str], str] = {}
    for source in sources:
        for row in source.records:
            key = _latent_key(row)
            _require_row_availability(row, "LATENT_FAMILY")
            availability[key] = str(row["available_at"])
            _add_latent_values(grouped[key], states[key], row)
            lineage[key].append(str(row.get("lineage_id", "")))
    output = []
    for key, values in sorted(grouped.items()):
        if not values:
            continue
        output.append({
            "underlying": key[0], "decision_time": key[1], "as_of_time": key[1],
            "available_at": availability[key], "availability_source": "P4_ROW_EXPLICIT",
            "horizon_group": key[2], "features": values,
            "missingness_mask": {name: value is None for name, value in values.items()},
            "feature_state_ids": states[key], "feature_metadata": {},
            "source_modalities": ["LATENT"], "quality_state": "PASS",
            "lineage_id": canonical_sha256(sorted(lineage[key])),
            "included_feature_ids": sorted(values), "excluded_feature_ids": [],
            "matched_filters": [],
        })
    return output


def _latent_key(row: dict[str, Any]) -> tuple[str, str, str]:
    key = (
        str(row.get("entity_id", "")), str(row.get("decision_time", "")),
        str(row.get("horizon_group", "")),
    )
    if not all(key):
        raise DataQualityError("P4 latent record lacks entity/time/horizon")
    return key


def _add_latent_values(
    target: dict[str, Any], states: dict[str, str], row: dict[str, Any],
) -> None:
    family = str(row.get("family_id", "GLOBAL"))
    representation = str(row.get("representation_type", "LATENT")).lower()
    values = row.get("component_values") or row.get("embedding_values") or []
    if not isinstance(values, list):
        raise DataQualityError("P4 latent values must be an array")
    for index, value in enumerate(values):
        name = f"{representation}.{family}.{index}"
        if name in target:
            raise DataQualityError(f"duplicate latent component: {name}")
        target[name] = value
    if row.get("fit_state_id"):
        states[f"{representation}.{family}"] = str(row["fit_state_id"])


def _missingness(value: Any) -> str:
    mapping = {
        "preserve_explicit_mask": "EXPLICIT_MASK",
        "mask_and_age_of_information": "EXPLICIT_MASK",
        "first_class_input": "EXPLICIT_MASK",
        "encoder_may_be_explicitly_skipped": "EXPLICIT_MASK",
        "unavailable_upstream": "EXPLICIT_MASK",
    }
    try:
        return mapping[str(value)]
    except KeyError as exc:
        raise ContractError(f"unsupported P4 missingness policy: {value}") from exc
