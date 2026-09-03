from __future__ import annotations

from datetime import datetime

import numpy as np

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .folds import rows_for_interval
from .matrix import build_group_matrices, impute_from_train
from .pca_models import fit_pca, fit_sparse_pca
from .records import RepresentationPolicy


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fit_candidates(train: np.ndarray, valid: np.ndarray, policy: RepresentationPolicy):
    pca = fit_pca(
        train,
        valid,
        policy.pca_variance_threshold,
        policy.max_components,
    )
    fits = [pca]
    if policy.sparse_pca_enabled:
        fits.append(
            fit_sparse_pca(
                train,
                valid,
                pca.components.shape[0],
                policy.sparse_alpha,
                policy.sparse_ridge_alpha,
                policy.sparse_max_iter,
                policy.sparse_tol,
                policy.random_state,
            )
        )
    return fits


def _fit_state_id(group, fold, fit, feature_ids) -> str:
    payload = {
        "family": group.family_id,
        "horizon": group.horizon_group,
        "fold": fold["fold_id"],
        "type": fit.representation_type,
        "features": feature_ids,
        "components": fit.components.tolist(),
    }
    return "repr:" + canonical_sha256(payload)[:20]


def _rmse(fit, valid: np.ndarray, observed: np.ndarray) -> float:
    if not observed.any():
        return 0.0
    residuals = (fit.reconstructed - valid)[observed]
    return float(np.sqrt(np.mean(residuals ** 2)))


def _append_fit_records(
    *, group, fold, fit, valid_idx, feature_ids, medians, valid, observed,
    matrix: ArtifactEnvelope, factor_records: list[dict], state_records: list[dict],
) -> None:
    state_id = _fit_state_id(group, fold, fit, feature_ids)
    for local, row_index in enumerate(valid_idx):
        decision_time, entity_id = group.row_keys[row_index]
        factor_records.append(
            {
                "decision_time": decision_time.isoformat(),
                "entity_id": entity_id,
                "available_at": group.available_at[row_index].isoformat().replace("+00:00", "Z"),
                "family_id": group.family_id,
                "horizon_group": group.horizon_group,
                "representation_type": fit.representation_type,
                "component_values": fit.scores[local].tolist(),
                "fit_state_id": state_id,
                "fold_id": fold["fold_id"],
                "lineage_id": matrix.lineage_id,
            }
        )
    state_records.append(
        {
            "fit_state_id": state_id,
            "fold_id": fold["fold_id"],
            "family_id": group.family_id,
            "horizon_group": group.horizon_group,
            "representation_type": fit.representation_type,
            "feature_ids": list(feature_ids),
            "components": fit.components.tolist(),
            "mean": fit.mean.tolist(),
            "imputation_medians": medians.tolist(),
            "explained_variance_ratio": fit.explained_variance_ratio.tolist(),
            "converged": fit.converged,
            "fit_start": fold["fit_start"],
            "fit_end": fold["fit_end"],
            "validation_reconstruction_rmse": _rmse(fit, valid, observed),
        }
    )


def _prepare_fold(group, fold, policy: RepresentationPolicy):
    train_idx = rows_for_interval(group.row_keys, _dt(fold["fit_start"]), _dt(fold["fit_end"]))
    valid_idx = rows_for_interval(
        group.row_keys, _dt(fold["transform_start"]), _dt(fold["transform_end"])
    )
    if len(train_idx) < policy.min_train_rows or not valid_idx:
        return None
    train, valid = group.values[train_idx], group.values[valid_idx]
    observed_columns = np.isfinite(train).any(axis=0)
    if int(observed_columns.sum()) < policy.min_features:
        return None
    candidate_train = train[:, observed_columns]
    candidate_valid = valid[:, observed_columns]
    candidate_observed = group.observed[valid_idx][:, observed_columns]
    candidate_features = np.asarray(group.feature_ids, dtype=object)[observed_columns]
    train_imputed, _ = impute_from_train(candidate_train, candidate_train)
    variable_columns = np.nanstd(train_imputed, axis=0) > 1e-12
    if int(variable_columns.sum()) < policy.min_features:
        return None
    train_final = train_imputed[:, variable_columns]
    valid_final, medians = impute_from_train(
        candidate_train[:, variable_columns], candidate_valid[:, variable_columns]
    )
    return (
        valid_idx,
        train_final,
        valid_final,
        candidate_observed[:, variable_columns],
        tuple(str(item) for item in candidate_features[variable_columns]),
        medians,
    )


def build_linear_representations(
    matrix: ArtifactEnvelope,
    folds: ArtifactEnvelope,
    policy: RepresentationPolicy,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    factor_records: list[dict[str, object]] = []
    state_records: list[dict[str, object]] = []
    for group in build_group_matrices(matrix):
        if len(group.feature_ids) < policy.min_features:
            continue
        for fold in folds.records:
            prepared = _prepare_fold(group, fold, policy)
            if prepared is None:
                continue
            valid_idx, train, valid, observed, feature_ids, medians = prepared
            for fit in _fit_candidates(train, valid, policy):
                _append_fit_records(
                    group=group,
                    fold=fold,
                    fit=fit,
                    valid_idx=valid_idx,
                    feature_ids=feature_ids,
                    medians=medians,
                    valid=valid,
                    observed=observed,
                    matrix=matrix,
                    factor_records=factor_records,
                    state_records=state_records,
                )
    lineage = canonical_sha256(
        {"matrix": matrix.artifact_id, "folds": folds.artifact_id, "module": "P4.S8.M02"}
    )
    return {
        "underlying_feature_factors_pca": build_artifact(
            artifact_name="underlying_feature_factors_pca",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S8.M02",
            context=context,
            grain=("decision_time", "entity_id", "family_id", "horizon_group", "representation_type"),
            records=factor_records,
            lineage_id=lineage,
            metadata={"source_matrix_id": matrix.artifact_id},
        ),
        "pca_fit_state_manifest": build_artifact(
            artifact_name="pca_fit_state_manifest",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S8.M02",
            context=context,
            grain=("fit_state_id",),
            records=state_records,
            lineage_id=lineage,
            metadata={"factor_artifact_name": "underlying_feature_factors_pca"},
        ),
    }
