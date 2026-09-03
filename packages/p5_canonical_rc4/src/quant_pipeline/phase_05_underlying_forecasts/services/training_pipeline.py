"""Leak-safe rolling training and observation-level OOF evidence."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.forecast import OOFValidationObservation
from ..errors import DataQualityError, ReasonCode
from .identifiers import as_utc, iso_utc, stable_hash, stable_id
from .modeling import get_resolver
from .tabular import align_features_targets, feature_rows
from .temporal_evaluation import select_target_folds


def train_spec(
    spec: dict[str, Any],
    view: dict[str, Any],
    targets: list[dict[str, Any]],
    plan: dict[str, Any],
    seed: int,
) -> tuple[dict[str, Any], list[OOFValidationObservation], list[dict[str, Any]]]:
    x_raw, y, aligned, feature_names = align_features_targets(
        feature_rows(view), targets, spec["target_id"], spec["horizon"]
    )
    folds = select_target_folds(plan, spec["target_id"], spec["horizon"])
    observations: list[OOFValidationObservation] = []
    runs: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    for fold_index, fold in enumerate(folds):
        trained, fold_observations, run = _train_fold(
            spec, x_raw, y, aligned, feature_names, fold, seed + fold_index,
        )
        final = trained
        observations.extend(fold_observations)
        runs.append(run)
    if final is None:
        raise DataQualityError("resolver produced no trained fold")
    final["rolling_refit_count"] = len(folds)
    final["training_runs"] = runs
    final["walk_forward_fold_ids"] = [fold["fold_id"] for fold in folds]
    return final, observations, runs


def _train_fold(
    spec: dict[str, Any],
    x_raw: np.ndarray,
    y: np.ndarray,
    aligned: list[dict[str, Any]],
    feature_names: tuple[str, ...],
    fold: dict[str, Any],
    seed: int,
) -> tuple[dict[str, Any], list[OOFValidationObservation], dict[str, Any]]:
    partitions = _partition_indices(aligned, fold)
    train_indices = partitions["TRAIN"]
    calibration_indices = partitions["CALIBRATION"]
    minimum = int(spec.get("minimum_sample", 8))
    if len(train_indices) < minimum or len(calibration_indices) < 3:
        raise DataQualityError(
            f"fold {fold['fold_id']} lacks required training/calibration history",
            reason_code=ReasonCode.INSUFFICIENT_HISTORY,
        )
    imputation = _fit_imputation(x_raw[train_indices])
    x = _apply_imputation(x_raw, imputation)
    resolver = get_resolver(spec["implementation_id"])
    state = resolver.fit(x[train_indices], y[train_indices], spec.get("parameters", {}), seed)
    predictions = resolver.predict(state, x)
    train_errors = y[train_indices] - predictions[train_indices]
    calibration_errors = y[calibration_indices] - predictions[calibration_indices]
    interval_std = max(float(np.std(train_errors, ddof=0)), 1e-12)
    residual_std = max(float(np.std(calibration_errors, ddof=0)), 1e-12)
    fit_cutoff = max(aligned[index]["available_at"] for index in train_indices)
    evidence_cutoff = max(aligned[index]["available_at"] for index in calibration_indices)
    hashes = _training_hashes(spec, aligned, train_indices, feature_names)
    model_id = stable_id(
        "model", spec["resolver_id"], fold["fold_id"], state, imputation.tolist(), hashes,
    )
    model = _model_record(
        spec, state, feature_names, imputation, fit_cutoff, evidence_cutoff,
        residual_std, interval_std, model_id, fold, hashes, seed,
    )
    observations = _oof_records(
        spec, aligned, y, predictions, interval_std, model_id, partitions, fold["fold_id"],
    )
    run = {
        "resolver_id": spec["resolver_id"],
        "model_artifact_id": model_id,
        "fold_id": fold["fold_id"],
        "fit_cutoff": iso_utc(fit_cutoff),
        "calibration_cutoff": iso_utc(evidence_cutoff),
        "training_sample_size": len(train_indices),
        "status": "TRAINED",
        "seed": seed,
        **hashes,
    }
    return model, observations, run


def _model_record(
    spec, state, feature_names, imputation, fit_cutoff, evidence_cutoff,
    residual_std, interval_std, model_id, fold, hashes, seed,
):
    return {
        **spec,
        "model_artifact_id": model_id,
        "model_state": state,
        "feature_names": feature_names,
        "imputation_values": imputation.tolist(),
        "fit_cutoff": iso_utc(fit_cutoff),
        "calibration_cutoff": iso_utc(evidence_cutoff),
        "training_cutoff": iso_utc(evidence_cutoff),
        "residual_std": residual_std,
        "validation_interval_std": interval_std,
        "fit_evidence_scope": "TRAIN_ONLY",
        "calibration_evidence_scope": "CALIBRATION_ONLY",
        "latest_fold_id": fold["fold_id"],
        "deterministic_seed": seed,
        "model_card": {
            "implementation_id": spec["implementation_id"],
            "target_id": spec["target_id"],
            "horizon": spec["horizon"],
            "role": spec["role"],
            "limitations": ["offline development evidence; sealed TEST not consumed"],
        },
        **hashes,
    }


def _training_hashes(spec, aligned, train_indices, feature_names):
    rows = [
        {
            "underlying": aligned[index]["underlying"],
            "prediction_timestamp": iso_utc(aligned[index]["prediction_timestamp"]),
            "available_at": iso_utc(aligned[index]["available_at"]),
            "lineage_id": aligned[index]["lineage_id"],
        }
        for index in train_indices
    ]
    return {
        "training_data_hash": stable_hash(rows),
        "feature_schema_hash": stable_hash(feature_names),
        "target_definition_hash": stable_hash(
            spec["target_id"], spec["horizon"], spec["unit"], spec.get("target_family")
        ),
        "model_implementation_id": spec["implementation_id"],
    }


def _oof_records(
    spec, aligned, y, predictions, residual_std, model_id, partitions, fold_id,
):
    records: list[OOFValidationObservation] = []
    for partition in ("VALIDATION", "CALIBRATION"):
        for index in partitions[partition]:
            row = aligned[index]
            prediction = float(predictions[index])
            records.append(OOFValidationObservation(
                observation_id=stable_id(
                    "oof", spec["resolver_id"], fold_id, row["underlying"],
                    row["prediction_timestamp"], partition,
                ),
                resolver_id=spec["resolver_id"],
                resolver_family=spec["resolver_family"],
                underlying=row["underlying"],
                target_id=spec["target_id"],
                horizon=spec["horizon"],
                unit=spec["unit"],
                prediction_timestamp=row["prediction_timestamp"],
                prediction=prediction,
                realized=float(y[index]),
                q05=prediction - 1.645 * residual_std,
                q95=prediction + 1.645 * residual_std,
                partition_id=partition,
                fold_id=fold_id,
                lineage_id=stable_id("oof-lineage", row["lineage_id"], model_id, fold_id),
            ))
    return records


def _partition_indices(aligned, fold):
    mapping = _partition_mapping(fold["partitions"])
    return {
        name: np.asarray([
            index for index, row in enumerate(aligned)
            if iso_utc(row["prediction_timestamp"]) in timestamps
        ], dtype=int)
        for name, timestamps in mapping.items()
    }


def _partition_mapping(value):
    if isinstance(value, dict):
        return {name: set(rows) for name, rows in value.items()}
    return {row["name"]: set(row["timestamps"]) for row in value}


def _fit_imputation(train: np.ndarray) -> np.ndarray:
    if train.ndim != 2:
        raise DataQualityError("training matrix must be two-dimensional")
    medians = np.nanmedian(train, axis=0)
    if np.any(~np.isfinite(medians)):
        raise DataQualityError("a feature is entirely missing in TRAIN")
    return medians


def _apply_imputation(matrix: np.ndarray, medians: np.ndarray) -> np.ndarray:
    output = np.asarray(matrix, dtype=float).copy()
    missing = ~np.isfinite(output)
    if np.any(missing):
        output[missing] = np.take(medians, np.where(missing)[1])
    return output
