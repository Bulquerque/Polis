from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact


def _time(value: object) -> datetime:
    if value is None:
        raise ValueError("timestamp is required")
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _artifact_dependencies(inputs: dict[str, ArtifactEnvelope]) -> dict[str, list[str]]:
    names = set(inputs)
    dependencies: dict[str, list[str]] = {
        "underlying_feature_matrix_raw": ["underlying_feature_matrix_selected"],
        "underlying_feature_matrix_selected": [
            "feature_selection_report",
            "feature_transform_state_manifest",
        ],
        "underlying_feature_factors_pca": [
            "underlying_feature_matrix_selected",
            "pca_fit_state_manifest",
            "representation_fold_plan",
        ],
        "underlying_feature_embeddings": [
            "underlying_feature_matrix_selected",
            "encoder_fit_state_manifest",
            "representation_fold_plan",
        ],
        "representation_quality_report": [
            "pca_fit_state_manifest",
            "encoder_fit_state_manifest",
        ],
        "feature_transform_state_manifest": [
            "causal_transform_fit_state_manifest",
            "normalization_neutralization_fit_state_manifest",
            "feature_selection_report",
        ],
        "feature_selection_report": ["feature_diversity_redundancy_report"],
    }
    return {
        name: [dependency for dependency in dependencies.get(name, []) if dependency in names]
        for name in names
    }


def _cycle_check(artifact: ArtifactEnvelope, reference: ArtifactEnvelope) -> dict[str, Any]:
    actual = (artifact.run_id, artifact.cycle_id, artifact.as_of_time.isoformat())
    expected = (reference.run_id, reference.cycle_id, reference.as_of_time.isoformat())
    return {
        "check_id": f"cycle:{artifact.artifact_name}",
        "scope": artifact.artifact_name,
        "check_type": "SNAPSHOT_CONSISTENCY",
        "status": "PASS" if actual == expected else "BLOCK",
        "observed": list(actual),
        "expected": list(expected),
        "severity": "ERROR" if actual != expected else "INFO",
    }


def _fit_state_checks(inputs: dict[str, ArtifactEnvelope]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    state_by_id: dict[str, dict[str, Any]] = {}
    for name in ("pca_fit_state_manifest", "encoder_fit_state_manifest"):
        for record in inputs[name].records:
            state_by_id[str(record["fit_state_id"])] = record
    for name in ("underlying_feature_factors_pca", "underlying_feature_embeddings"):
        for index, record in enumerate(inputs[name].records):
            state = state_by_id.get(str(record.get("fit_state_id")))
            decision_time = _time(record["decision_time"])
            status = "PASS"
            observed: object = record.get("fit_state_id")
            expected: object = "known fit_state_id with fit_end < decision_time"
            if state is None:
                status = "BLOCK"
            elif _time(state["fit_end"]) >= decision_time:
                status = "BLOCK"
                observed = state["fit_end"]
            checks.append(
                {
                    "check_id": f"fit:{name}:{index}",
                    "scope": name,
                    "check_type": "FIT_BEFORE_USE",
                    "status": status,
                    "observed": observed,
                    "expected": expected,
                    "severity": "ERROR" if status == "BLOCK" else "INFO",
                }
            )
    return checks


def _causal_checks(inputs: dict[str, ArtifactEnvelope]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    stateless = {"identity", "signed_log1p"}
    for index, record in enumerate(inputs["causal_transform_fit_state_manifest"].records):
        fit_end_raw = record.get("fit_end")
        apply_start_raw = record.get("apply_start")
        transform_type = str(record.get("transform_type") or "")
        if fit_end_raw is None:
            status = "PASS" if transform_type in stateless and apply_start_raw is not None else "BLOCK"
            observed: object = "STATELESS" if status == "PASS" else fit_end_raw
            expected = "stateless transform with apply_start"
        else:
            fit_end = _time(fit_end_raw)
            apply_start = _time(apply_start_raw)
            status = "PASS" if fit_end < apply_start else "BLOCK"
            observed = fit_end_raw
            expected = f"before {apply_start_raw}"
        checks.append(
            {
                "check_id": f"causal-fit:{index}",
                "scope": str(record["feature_id"]),
                "check_type": "CAUSAL_TRANSFORM_FIT",
                "status": status,
                "observed": observed,
                "expected": expected,
                "severity": "ERROR" if status == "BLOCK" else "INFO",
            }
        )
    return checks


def _fold_checks(inputs: dict[str, ArtifactEnvelope]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for record in inputs["representation_fold_plan"].records:
        status = "PASS" if _time(record["fit_end"]) < _time(record["transform_start"]) else "BLOCK"
        checks.append(
            {
                "check_id": f"fold:{record['fold_id']}",
                "scope": str(record["fold_id"]),
                "check_type": "FOLD_TEMPORAL_ORDER",
                "status": status,
                "observed": record["fit_end"],
                "expected": f"before {record['transform_start']}",
                "severity": "ERROR" if status == "BLOCK" else "INFO",
            }
        )
    return checks


def _feature_records(inputs: dict[str, ArtifactEnvelope]) -> list[dict[str, Any]]:
    matrix = inputs["underlying_feature_matrix_selected"]
    transform_records = {
        (str(item["horizon_group"]), str(item["feature_id"])): item
        for item in inputs["feature_transform_state_manifest"].records
    }
    records: list[dict[str, Any]] = []
    for key, item in sorted(matrix.metadata.get("feature_catalog", {}).items()):
        lookup = (str(item["horizon_group"]), str(item["feature_id"]))
        state = transform_records.get(lookup)
        dependencies = [] if state is None else [
            *state.get("causal_fit_state_ids", []),
            *state.get("normalization_state_ids", []),
        ]
        records.append(
            {
                "node_id": f"feature:{key}",
                "node_type": "FEATURE",
                "artifact_name": matrix.artifact_name,
                "producer_module_id": "P4.S7.M04",
                "dependencies": dependencies,
                "lineage_status": "COMPLETE" if state is not None else "INCOMPLETE",
                "temporal_status": "PASS" if state is not None else "BLOCK",
                "content_hash": canonical_sha256(item),
                "record_count": matrix.record_count,
                "issues": [] if state is not None else ["TRANSFORM_STATE_MISSING"],
            }
        )
    return records


def _artifact_lineage_records(
    inputs: dict[str, ArtifactEnvelope], reference: ArtifactEnvelope
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dependencies = _artifact_dependencies(inputs)
    records: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    for name, artifact in sorted(inputs.items()):
        if name in {"s9_policy_registry", "research_attempt_event_log"}:
            continue
        cycle = _cycle_check(artifact, reference)
        checks.append(cycle)
        records.append({
            "node_id": artifact.artifact_id, "node_type": "ARTIFACT", "artifact_name": name,
            "producer_module_id": artifact.producer_module_id,
            "dependencies": [inputs[item].artifact_id for item in dependencies.get(name, [])],
            "lineage_status": "COMPLETE" if cycle["status"] == "PASS" else "INCOMPLETE",
            "temporal_status": cycle["status"], "content_hash": artifact.content_hash,
            "record_count": artifact.record_count,
            "issues": [] if cycle["status"] == "PASS" else ["SNAPSHOT_MISMATCH"],
        })
    return records, checks


def build_lineage_outputs(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    reference = inputs["underlying_feature_matrix_selected"]
    lineage_records, cycle_checks = _artifact_lineage_records(inputs, reference)
    lineage_records.extend(_feature_records(inputs))
    temporal_checks = [*cycle_checks, *_causal_checks(inputs), *_fold_checks(inputs), *_fit_state_checks(inputs)]
    blocked = sum(item["status"] == "BLOCK" for item in temporal_checks)
    lineage = canonical_sha256({"inputs": sorted(item.artifact_id for item in inputs.values()), "blocked": blocked})
    quality = "BLOCKED" if blocked else "VALIDATED"
    status = "BLOCKED" if blocked else "PRODUCED"
    return {
        "feature_lineage_report": build_artifact(
            artifact_name="feature_lineage_report", schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M01", context=context, grain=("node_id",),
            records=lineage_records, lineage_id=lineage,
            metadata={"dependency_model": "artifact-and-feature-graph", "openlineage_inspired": True},
            execution_status=status, quality_status=quality,
        ),
        "temporal_safety_report": build_artifact(
            artifact_name="temporal_safety_report", schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M01", context=context, grain=("check_id",),
            records=temporal_checks, lineage_id=lineage, metadata={"blocked_check_count": blocked},
            execution_status=status, quality_status=quality,
        ),
    }
