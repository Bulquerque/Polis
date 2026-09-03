"""Immutable P4 data projections used by the P5 compatibility boundary."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

def adapt_p4_research_for_p5(outputs: dict[str, Any]) -> dict[str, Any]:
    """Translate P4 signed consensus into P5's bounded diagnostic metric."""
    names = (
        "approved_hypothesis_passport_registry",
        "hypothesis_budget_report",
        "research_attempt_ledger",
        "rejected_feature_graveyard",
        "feature_observer_registry",
        "perspective_conflict_panel",
    )
    result = {name: deepcopy(outputs[name]) for name in names if name in outputs}
    conflicts = result.get("perspective_conflict_panel")
    if not isinstance(conflicts, dict):
        return result
    for row in conflicts.get("records", []):
        value = row.get("consensus_score")
        if value is None:
            continue
        number = float(value)
        mode = str(row.get("mode", ""))
        if mode == "SIGNED_DIRECTIONAL":
            if not -1.0 <= number <= 1.0:
                raise RuntimeError("P4 signed consensus_score is outside [-1, 1]")
            row.setdefault("attributes", {})["p4_signed_consensus_score"] = number
            row["consensus_score"] = (number + 1.0) / 2.0
        elif not 0.0 <= number <= 1.0:
            raise RuntimeError("P4 bounded consensus_score is outside [0, 1]")
    conflicts.setdefault("metadata", {})["p5_adapter"] = {
        "name": "signed_consensus_to_bounded_consensus",
        "version": "P4-P5-ADAPTER-1",
        "source_artifact_id": conflicts.get("artifact_id"),
    }
    return result


def build_p5_outcome_bundle_from_p4(outputs: dict[str, Any]) -> dict[str, Any]:
    """Build forward labels from observed P4 price returns without inventing values."""
    artifact = outputs.get("price_return_atomic_panel", {})
    rows = [
        row for row in artifact.get("records", [])
        if row.get("feature_id") == "price.log_return_1" and row.get("value") is not None
    ]
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_entity.setdefault(str(row["entity_id"]), []).append(row)
    outcomes: list[dict[str, Any]] = []
    horizon_specs = (("5D", "excess_return_5d", 5, 1),)
    for entity, entity_rows in sorted(by_entity.items()):
        entity_rows.sort(key=lambda row: str(row["decision_time"]))
        for horizon, target_id, offset, prediction_stride in horizon_specs:
            valid_end = len(entity_rows) - offset
            prediction_indices = list(range(0, valid_end, prediction_stride))
            for index in prediction_indices:
                current = entity_rows[index]
                future = entity_rows[index + offset]
                prediction = str(current["decision_time"])
                label_end = str(future["available_at"])
                if label_end <= prediction:
                    continue
                outcomes.append({
                    "underlying": entity,
                    "prediction_timestamp": prediction,
                    "label_end_time": label_end,
                    "available_at": label_end,
                    "target_id": target_id,
                    "horizon": horizon,
                    "unit": "decimal_return",
                    "value": float(future["value"]),
                    "lineage_id": f"p4-forward-label:{horizon}:" + ":".join(
                        (str(current.get("record_lineage_id", "")), str(future.get("record_lineage_id", "")))
                    ),
                })
    if len(outcomes) < 12:
        raise RuntimeError(f"P4 did not provide enough forward labels for P5: {len(outcomes)}")
    by_prediction: dict[str, list[dict[str, Any]]] = {}
    for row in outcomes:
        by_prediction.setdefault(str(row["prediction_timestamp"]), []).append(row)
    expected_entities = sorted({str(row["underlying"]) for row in outcomes})
    balanced = [
        row for row in outcomes
        if len(by_prediction[str(row["prediction_timestamp"])]) == len(expected_entities)
    ]
    if len(balanced) < 12:
        raise RuntimeError(
            "P4 did not provide enough balanced forward labels for P5: "
            f"{len(balanced)} of {len(outcomes)}"
        )
    return {
        "records": balanced,
        "metadata": {
            "adapter": "p4_price_return_forward_label",
            "version": "P4-P5-OUTCOME-ADAPTER-1",
            "source_artifact": artifact.get("artifact_id"),
            "source_feature_id": "price.log_return_1",
            "target_horizons": ["5D"],
            "values_fabricated": False,
            "cross_section_filter": {
                "mode": "FULL_EXPECTED_ENTITY_SET",
                "expected_entities": expected_entities,
                "input_record_count": len(outcomes),
                "retained_record_count": len(balanced),
            },
        },
    }


def _rebuild_p4_artifact(artifact: dict[str, Any], records: list[dict[str, Any]], metadata: dict[str, Any], *,
                         execution_status: str | None = None, quality_status: str | None = None,
                         lineage_id: str | None = None) -> dict[str, Any]:
    """Re-issue one content-addressed P4 envelope after a declared P5 projection."""
    from quant_pipeline.common.hashing.hash_utils import canonical_sha256

    alias_of = artifact.get("alias_of")
    content_hash = canonical_sha256({"records": records, "metadata": metadata, "alias_of": alias_of})
    return {
        **artifact,
        "artifact_id": f'{artifact["artifact_name"]}:{content_hash[:16]}',
        "content_hash": content_hash,
        "record_count": len(records),
        "records": records,
        "metadata": metadata,
        "lineage_id": lineage_id or artifact["lineage_id"],
        "execution_status": execution_status or artifact["execution_status"],
        "quality_status": quality_status or artifact["quality_status"],
    }


def _rebuild_p4_envelope_hash(artifact: dict[str, Any]) -> dict[str, Any]:
    from quant_pipeline.common.hashing.hash_utils import canonical_sha256

    records = artifact["records"]
    metadata = artifact.get("metadata", {})
    alias_of = artifact.get("alias_of")
    content_hash = canonical_sha256({"records": records, "metadata": metadata, "alias_of": alias_of})
    return {
        **artifact,
        "artifact_id": f'{artifact["artifact_name"]}:{content_hash[:16]}',
        "content_hash": content_hash,
        "record_count": len(records),
    }


def adapt_p4_feature_matrix_for_p5(
    p4: dict[str, Any], outcome_bundle: dict[str, Any], p5_source: Path,
) -> dict[str, Any]:
    """Project P4 features to the first P5 train window without inventing values.

    P4 may legitimately expose an expanding feature whose first observations are
    unavailable. P5's canonical imputer rejects a column that is empty in TRAIN,
    so the boundary removes only features with no observed value in the exact
    first TRAIN partition. The original P4 artifact remains untouched; the
    content-addressed projection and its lineage are published to P5.
    """
    from quant_pipeline.phase_05_underlying_forecasts.services.tabular import target_rows
    from quant_pipeline.phase_05_underlying_forecasts.services.temporal_evaluation import build_evaluation_plan

    handoff = p4["outputs"]["phase5_feature_handoff_manifest"]
    as_of = datetime.fromisoformat(handoff["as_of_time"].replace("Z", "+00:00"))
    targets = target_rows(outcome_bundle, training_cutoff=as_of)
    plan, _receipt = build_evaluation_plan(targets, window_type="EXPANDING")
    target_plan = plan["target_plans"][0]
    first_fold = target_plan["folds"][0]
    train_timestamps = {
        str(timestamp).replace("+00:00", "Z")
        for timestamp in first_fold["partitions"][0]["timestamps"]
    }

    original = deepcopy(p4["catalog"]["underlying_feature_matrix_selected"])
    raw_records = original["records"]
    observed_features: set[str] = set()
    all_features: set[str] = set()
    for row in raw_records:
        values = row.get("values", {})
        all_features.update(str(name) for name in values)
        if str(row.get("decision_time")) in train_timestamps:
            observed_features.update(
                str(name) for name, value in values.items() if value is not None
            )
    removed = sorted(all_features - observed_features)
    if not observed_features:
        raise RuntimeError("P4-to-P5 feature projection found no observed TRAIN feature")
    if not removed:
        return {"status": "NOT_REQUIRED", "removed_features": [], "train_timestamp_count": len(train_timestamps)}

    def projected_record(row: dict[str, Any]) -> dict[str, Any]:
        output = deepcopy(row)
        for field in ("values", "raw_values", "transformed_values", "normalized_values", "neutralized_values",
                      "missingness_mask", "feature_state_ids"):
            if isinstance(output.get(field), dict):
                output[field] = {
                    name: value for name, value in output[field].items()
                    if str(name) in observed_features
                }
        return output

    records = [projected_record(row) for row in raw_records]
    metadata = deepcopy(original.get("metadata", {}))
    metadata["p5_adapter"] = {
        "name": "p4_train_visible_feature_projection",
        "version": "P4-P5-FEATURE-ADAPTER-1",
        "source_artifact_id": original["artifact_id"],
        "source_content_hash": original["content_hash"],
        "target_id": target_plan["target_id"],
        "horizon": target_plan["horizon"],
        "first_train_timestamp_count": len(train_timestamps),
        "removed_features": removed,
        "values_fabricated": False,
    }
    adapted = _rebuild_p4_artifact(
        original,
        records,
        metadata,
        execution_status="DEGRADED",
        quality_status="DEGRADED",
        lineage_id=f'p4-p5-feature-adapter:{original["lineage_id"]}',
    )
    old_id = original["artifact_id"]
    new_id = adapted["artifact_id"]

    p4["catalog"]["underlying_feature_matrix_selected"] = adapted
    p4["outputs"]["underlying_feature_matrix_selected"] = adapted
    handoff = deepcopy(p4["outputs"]["phase5_feature_handoff_manifest"])
    for row in handoff["records"]:
        if row.get("artifact_name") == "underlying_feature_matrix_selected":
            row.update({
                key: adapted[key]
                for key in ("artifact_id", "content_hash", "schema_version", "record_count", "grain",
                            "execution_status", "quality_status")
            })
    manifest = deepcopy(p4["outputs"]["model_consumer_view_manifest"])
    for row in manifest["records"]:
        row["artifact_ids"] = [new_id if item == old_id else item for item in row.get("artifact_ids", [])]
    manifest = _rebuild_p4_envelope_hash(manifest)
    bundle = deepcopy(p4["outputs"]["model_consumer_view_bundle"])
    for row in bundle["records"]:
        for reference in row.get("artifact_references", []):
            if reference.get("artifact_id") == old_id:
                reference.update({
                    "artifact_id": new_id,
                    "content_hash": adapted["content_hash"],
                    "record_count": adapted["record_count"],
                    "execution_status": adapted["execution_status"],
                })
    bundle = _rebuild_p4_envelope_hash(bundle)
    handoff["metadata"] = {
        **handoff.get("metadata", {}),
        "consumer_view_manifest_id": manifest["artifact_id"],
        "consumer_view_manifest_hash": manifest["content_hash"],
        "p5_adapter": metadata["p5_adapter"],
    }
    handoff = _rebuild_p4_envelope_hash(handoff)
    for name, value in (
        ("phase5_feature_handoff_manifest", handoff),
        ("model_consumer_view_manifest", manifest),
        ("model_consumer_view_bundle", bundle),
    ):
        p4["outputs"][name] = value
    p4["summary"].update({
        "handoff_sha256": handoff["content_hash"],
        "lineage_id": handoff["lineage_id"],
        "p5_feature_adapter": metadata["p5_adapter"],
    })
    return {
        "status": "APPLIED",
        "removed_features": removed,
        "retained_features": sorted(observed_features),
        "train_timestamp_count": len(train_timestamps),
        "source_artifact_id": old_id,
        "adapted_artifact_id": new_id,
    }


