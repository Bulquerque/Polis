from __future__ import annotations

from datetime import datetime

import numpy as np

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .encoder_backend import torch_available, train_encoder
from .folds import rows_for_interval
from .matrix import build_group_matrices, impute_from_train
from .records import RepresentationPolicy


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _skipped(
    context: ExecutionContext,
    reason: str,
    matrix: ArtifactEnvelope,
) -> dict[str, ArtifactEnvelope]:
    metadata = {"skip_reason": reason, "source_matrix_id": matrix.artifact_id}
    outputs: dict[str, ArtifactEnvelope] = {}
    for name in (
        "underlying_feature_embeddings",
        "encoder_fit_state_manifest",
    ):
        grain = ("fit_state_id",) if name.endswith("manifest") else (
            "decision_time",
            "entity_id",
        )
        outputs[name] = build_artifact(
            artifact_name=name,
            schema_version="v14.9-rc1",
            producer_module_id="P4.S8.M03",
            context=context,
            grain=grain,
            records=[],
            lineage_id=canonical_sha256(metadata),
            metadata=metadata,
            execution_status="SKIPPED_NOT_AUTHORIZED",
            quality_status="NOT_EVALUATED",
        )
    return outputs


def _inner_indices(group, train_idx: list[int]) -> tuple[list[int], list[int]]:
    times = sorted({group.row_keys[index][0] for index in train_idx})
    split = max(2, min(len(times) - 1, int(len(times) * 0.8)))
    inner_train_times = set(times[:split])
    inner_valid_times = set(times[split:])
    return (
        [index for index in train_idx if group.row_keys[index][0] in inner_train_times],
        [index for index in train_idx if group.row_keys[index][0] in inner_valid_times],
    )


def _observed_rmse(
    reconstructed: np.ndarray,
    expected: np.ndarray,
    observed: np.ndarray,
) -> float:
    errors = (reconstructed - expected)[observed]
    return float(np.sqrt(np.mean(errors**2))) if errors.size else 0.0


def _embedding_records(
    *,
    group,
    valid_idx: list[int],
    result,
    state_id: str,
    fold_id: str,
    lineage_id: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for local_index, row_index in enumerate(valid_idx):
        decision_time, entity_id = group.row_keys[row_index]
        records.append(
            {
                "decision_time": decision_time.isoformat(),
                "entity_id": entity_id,
                "available_at": group.available_at[row_index].isoformat().replace("+00:00", "Z"),
                "family_id": group.family_id,
                "horizon_group": group.horizon_group,
                "shared_latent": result.shared[local_index].tolist(),
                "private_latents": {
                    name: value[local_index].tolist()
                    for name, value in result.private.items()
                },
                "fit_state_id": state_id,
                "fold_id": fold_id,
                "config_id": result.config_id,
                "lineage_id": lineage_id,
            }
        )
    return records


def _state_record(
    *,
    group,
    fold: dict[str, object],
    inner_train_idx: list[int],
    inner_valid_idx: list[int],
    medians: np.ndarray,
    result,
    state_id: str,
    transform: np.ndarray,
    valid_idx: list[int],
) -> dict[str, object]:
    return {
        "fit_state_id": state_id,
        "fold_id": fold["fold_id"],
        "family_id": group.family_id,
        "horizon_group": group.horizon_group,
        "config_id": result.config_id,
        "feature_ids": list(group.feature_ids),
        "modalities": {name: list(value) for name, value in group.modalities.items()},
        "imputation_medians": medians.tolist(),
        "model_state": result.state,
        "search_records": result.search_records,
        "validation_reconstruction_rmse": _observed_rmse(
            result.reconstructed,
            transform,
            group.observed[valid_idx],
        ),
        "inner_fit_end": group.row_keys[inner_train_idx[-1]][0].isoformat(),
        "inner_validation_start": group.row_keys[inner_valid_idx[0]][0].isoformat(),
        "fit_start": fold["fit_start"],
        "fit_end": fold["fit_end"],
    }


def _fold_indices(group, fold: dict[str, object], policy: RepresentationPolicy):
    train_idx = rows_for_interval(
        group.row_keys,
        _dt(fold["fit_start"]),
        _dt(fold["fit_end"]),
    )
    valid_idx = rows_for_interval(
        group.row_keys,
        _dt(fold["transform_start"]),
        _dt(fold["transform_end"]),
    )
    if len(train_idx) < policy.encoder_min_train_rows or not valid_idx:
        return None
    inner_train_idx, inner_valid_idx = _inner_indices(group, train_idx)
    if not inner_train_idx or not inner_valid_idx:
        return None
    return train_idx, valid_idx, inner_train_idx, inner_valid_idx


def _imputed_fold_matrices(group, indices):
    train_idx, valid_idx, inner_train_idx, inner_valid_idx = indices
    final_train, medians = impute_from_train(
        group.values[train_idx], group.values[train_idx]
    )
    transform, _ = impute_from_train(
        group.values[train_idx], group.values[valid_idx]
    )
    inner_train, _ = impute_from_train(
        group.values[inner_train_idx], group.values[inner_train_idx]
    )
    inner_valid, _ = impute_from_train(
        group.values[inner_train_idx], group.values[inner_valid_idx]
    )
    matrices = {
        "final_train": final_train,
        "transform": transform,
        "inner_train": inner_train,
        "inner_valid": inner_valid,
    }
    return matrices, medians


def _train_encoder_for_fold(group, indices, matrices, policy: RepresentationPolicy):
    train_idx, valid_idx, inner_train_idx, inner_valid_idx = indices
    return train_encoder(
        inner_train=matrices["inner_train"],
        inner_train_observed=group.observed[inner_train_idx],
        inner_validation=matrices["inner_valid"],
        inner_validation_observed=group.observed[inner_valid_idx],
        final_train=matrices["final_train"],
        final_train_observed=group.observed[train_idx],
        transform=matrices["transform"],
        transform_observed=group.observed[valid_idx],
        modalities=group.modalities,
        configs=policy.encoder_configurations,
        max_epochs=policy.encoder_max_epochs,
        patience=policy.encoder_patience,
        learning_rate=policy.encoder_learning_rate,
        weight_decay=policy.encoder_weight_decay,
        huber_delta=policy.encoder_huber_delta,
        random_state=policy.random_state,
    )


def _encoder_state_id(group, fold: dict[str, object], result) -> str:
    return "encoder:" + canonical_sha256(
        {
            "family": group.family_id,
            "horizon": group.horizon_group,
            "fold": fold["fold_id"],
            "config": result.config_id,
            "weights": result.state["weights"],
        }
    )[:20]


def _train_fold(
    *,
    group,
    fold: dict[str, object],
    indices,
    matrix: ArtifactEnvelope,
    policy: RepresentationPolicy,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    _, valid_idx, inner_train_idx, inner_valid_idx = indices
    matrices, medians = _imputed_fold_matrices(group, indices)
    result = _train_encoder_for_fold(group, indices, matrices, policy)
    state_id = _encoder_state_id(group, fold, result)
    embeddings = _embedding_records(
        group=group,
        valid_idx=valid_idx,
        result=result,
        state_id=state_id,
        fold_id=str(fold["fold_id"]),
        lineage_id=matrix.lineage_id,
    )
    state = _state_record(
        group=group,
        fold=fold,
        inner_train_idx=inner_train_idx,
        inner_valid_idx=inner_valid_idx,
        medians=medians,
        result=result,
        state_id=state_id,
        transform=matrices["transform"],
        valid_idx=valid_idx,
    )
    return embeddings, state

def _encoder_outputs(
    *,
    matrix: ArtifactEnvelope,
    context: ExecutionContext,
    embedding_records: list[dict[str, object]],
    state_records: list[dict[str, object]],
) -> dict[str, ArtifactEnvelope]:
    lineage = canonical_sha256(
        {
            "matrix": matrix.artifact_id,
            "module": "P4.S8.M03",
            "state_ids": [record["fit_state_id"] for record in state_records],
        }
    )
    execution_status = "PRODUCED" if embedding_records else "SKIPPED_NOT_AUTHORIZED"
    quality_status = "VALIDATED" if embedding_records else "NOT_EVALUATED"
    return {
        "underlying_feature_embeddings": build_artifact(
            artifact_name="underlying_feature_embeddings",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S8.M03",
            context=context,
            grain=("decision_time", "entity_id", "family_id", "horizon_group"),
            records=embedding_records,
            lineage_id=lineage,
            metadata={"source_matrix_id": matrix.artifact_id},
            execution_status=execution_status,
            quality_status=quality_status,
        ),
        "encoder_fit_state_manifest": build_artifact(
            artifact_name="encoder_fit_state_manifest",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S8.M03",
            context=context,
            grain=("fit_state_id",),
            records=state_records,
            lineage_id=lineage,
            metadata={"embedding_artifact_name": "underlying_feature_embeddings"},
            execution_status=execution_status,
            quality_status=quality_status,
        ),
    }


def build_encoder_representations(
    matrix: ArtifactEnvelope,
    folds: ArtifactEnvelope,
    decision: ArtifactEnvelope,
    policy: RepresentationPolicy,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    authorization = str(decision.records[0]["decision"])
    if authorization != "AUTHORIZED" or not torch_available():
        reason = authorization if authorization != "AUTHORIZED" else "PYTORCH_UNAVAILABLE"
        return _skipped(context, reason, matrix)

    embedding_records: list[dict[str, object]] = []
    state_records: list[dict[str, object]] = []
    for group in build_group_matrices(matrix):
        if (
            len(group.feature_ids) < policy.min_features
            or len(group.modalities) < policy.encoder_min_modalities
        ):
            continue
        for fold in folds.records:
            indices = _fold_indices(group, fold, policy)
            if indices is None:
                continue
            embeddings, state = _train_fold(
                group=group,
                fold=fold,
                indices=indices,
                matrix=matrix,
                policy=policy,
            )
            embedding_records.extend(embeddings)
            state_records.append(state)
    return _encoder_outputs(
        matrix=matrix,
        context=context,
        embedding_records=embedding_records,
        state_records=state_records,
    )
