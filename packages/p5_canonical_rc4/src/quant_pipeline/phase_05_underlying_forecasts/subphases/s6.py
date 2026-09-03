"""S6: covariance, dynamic correlation, network dependence and champion selection."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.core import HandlerOutcome
from ..errors import DataQualityError
from ..services.dependence import (
    covariance_holdout_score,
    covariance_to_correlation,
    dcc_covariance,
    dependence_stability,
    network_dependence,
    shrinkage_covariances,
    validate_covariance,
)
from ..services.identifiers import stable_id
from ..services.oof_evidence import active_target_horizon, residual_matrix


def m01(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, entities, matrix, cutoff = _matrix(payload)
    train = _estimation_sample(matrix)
    records = [
        _matrix_record(
            method, model, entities, covariance, cutoff, as_of_time, len(train), matrix,
            covariance_type="FORECAST_ERROR_COVARIANCE",
        )
        for method, covariance in shrinkage_covariances(train).items()
    ]
    return HandlerOutcome(values=({"records": records},))


def m02(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, entities, matrix, cutoff = _matrix(payload)
    train = _estimation_sample(matrix)
    covariance, diagnostics = dcc_covariance(train)
    market = np.mean(train, axis=1)
    variance = max(float(np.var(market, ddof=1)), 1e-12)
    betas = {
        entity: float(np.cov(train[:, index], market, ddof=1)[0, 1] / variance)
        for index, entity in enumerate(entities)
    }
    record = _matrix_record(
        "DCC", model, entities, covariance, cutoff, as_of_time, len(train), matrix,
        covariance_type="DYNAMIC_FORECAST_ERROR_COVARIANCE",
    )
    record.update({"betas": betas, "dcc_diagnostics": diagnostics})
    return HandlerOutcome(values=({"records": [record]},))


def m03(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, entities, matrix, cutoff = _matrix(payload)
    network = network_dependence(_estimation_sample(matrix), entities)
    record = {
        "registry_id": stable_id("network", model["model_artifact_id"], network, cutoff),
        "method": "SPARSE_OOF_RESIDUAL_CORRELATION_NETWORK",
        "view_id": model["feature_view_id"],
        "target_id": model["target_id"],
        "horizon": model["horizon"],
        "as_of_time": as_of_time.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "lineage_id": stable_id("network-lineage", model["model_artifact_id"], cutoff),
        "sample_size": len(matrix),
        "conditioning": "RETURN_FORECAST_OOF_RESIDUAL",
        "threshold_version": "TOP_K_ABSOLUTE_CORRELATION_V2",
        "network_regime": "CURRENT_OOF_WINDOW",
        **network,
    }
    return HandlerOutcome(values=({"records": [record]},))


def m04(payload: dict[str, Any]) -> HandlerOutcome:
    source = _source_records(payload)
    matrices = [row for row in source if "matrix" in row]
    networks = [row for row in source if "edges" in row and "matrix" not in row]
    if not matrices:
        raise DataQualityError("covariance validation requires matrix records")
    validated_matrices = [_validate_matrix_record(row) for row in matrices]
    champion = min(
        validated_matrices,
        key=lambda row: (
            float(row["oos_log_score"]),
            float(row["diagnostics"]["repair_ratio"]),
            float(row["diagnostics"]["condition_number"]),
            str(row["method"]),
        ),
    )
    for row in validated_matrices:
        row["champion_status"] = "CHAMPION" if row["registry_id"] == champion["registry_id"] else "QUALIFIED_CHALLENGER"
    validated_networks = [_validate_network_record(row, champion) for row in networks]
    registry = validated_matrices + validated_networks
    reports = [_matrix_report(row) for row in validated_matrices] + [_network_report(row) for row in validated_networks]
    return HandlerOutcome(values=(
        {
            "records": registry,
            "champion_registry_id": champion["registry_id"],
            "selection_scope": {
                "target_id": champion["target_id"],
                "horizon": champion["horizon"],
                "entities": champion["entities"],
                "as_of_time": champion["as_of_time"],
            },
        },
        {"records": reports, "rejected_records": [], "selection_metric": "OOS_GAUSSIAN_LOG_SCORE"},
    ))


def _validate_matrix_record(row: dict[str, Any]) -> dict[str, Any]:
    repaired, diagnostics = validate_covariance(np.asarray(row["matrix"], dtype=float), repair=True, max_repair_ratio=0.10)
    identifier = stable_id("validated-covariance", row["registry_id"], diagnostics)
    return {
        **row,
        "registry_id": identifier,
        "matrix": repaired.tolist(),
        "correlation_matrix": covariance_to_correlation(repaired).tolist(),
        "diagnostics": diagnostics,
        "validated": True,
        "psd_status": "REPAIRED" if diagnostics["repair_applied"] else "PSD",
        "repair_magnitude": diagnostics["repair_ratio"],
    }


def _validate_network_record(row: dict[str, Any], champion: dict[str, Any]) -> dict[str, Any]:
    edges = row.get("edges", [])
    entities = tuple(row.get("entities", ()))
    if not entities or any(edge.get("source") not in entities or edge.get("target") not in entities for edge in edges):
        raise DataQualityError("dependence network contains invalid nodes or edges")
    return {
        **row,
        "registry_id": stable_id("validated-network", row["registry_id"], edges),
        "validated": True,
        "artifact_type": "DEPENDENCE_NETWORK",
        "consumer_module_id": "P5.S6.M04",
        "champion_covariance_registry_id": champion["registry_id"],
        "champion_status": "QUALIFIED_SIDECAR",
    }


def _matrix_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_registry_id": row["source_registry_id"],
        "validated_registry_id": row["registry_id"],
        "artifact_type": "COVARIANCE_MATRIX",
        "method": row["method"],
        "oos_log_score": row["oos_log_score"],
        "champion_status": row["champion_status"],
        **row["diagnostics"],
    }


def _network_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_registry_id": row.get("source_registry_id", row["registry_id"]),
        "validated_registry_id": row["registry_id"],
        "artifact_type": "DEPENDENCE_NETWORK",
        "edge_count": len(row.get("edges", [])),
        "component_count": len(row.get("connected_components", [])),
        "consumer_module_id": row["consumer_module_id"],
        "validated": True,
    }


def _matrix(payload):
    target_id, horizon = active_target_horizon(payload, require_current=False)
    return residual_matrix(
        payload.get("oof_validation_observation_panel"),
        _mapping(payload, "qualified_resolver_registry"),
        target_id=target_id, horizon=horizon,
    )


def _matrix_record(method, model, entities, matrix, cutoff, as_of_time, sample_size, full_sample, covariance_type):
    diagnostics = dependence_stability(full_sample, matrix)
    source_id = stable_id("covariance", method, model["model_artifact_id"], entities, matrix.tolist(), cutoff)
    return {
        "registry_id": source_id,
        "source_registry_id": source_id,
        "method": method,
        "covariance_type": covariance_type,
        "entities": entities,
        "matrix": matrix.tolist(),
        "view_id": model["feature_view_id"],
        "target_id": model["target_id"],
        "horizon": model["horizon"],
        "as_of_time": as_of_time.isoformat(),
        "evidence_cutoff": cutoff.isoformat(),
        "lineage_id": stable_id("covariance-lineage", model["model_artifact_id"], method, cutoff),
        "sample_size": sample_size,
        "effective_sample_size": sample_size,
        "conditioning": "RETURN_FORECAST_OOF_RESIDUAL",
        "oos_log_score": covariance_holdout_score(full_sample, matrix),
        "stability": diagnostics,
    }


def _source_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for name, value in payload.items()
        if name.startswith("covariance_member_registry_") and isinstance(value, dict)
        for row in value.get("records", [])
    ]


def _estimation_sample(matrix: np.ndarray) -> np.ndarray:
    cut = min(max(20, int(round(len(matrix) * 0.80))), len(matrix) - 5)
    return matrix[:cut]


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
