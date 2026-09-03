"""S2: declarative targets, multifold temporal evaluation and qualification."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..domain.core import HandlerOutcome
from ..domain.forecast import OOFValidationObservationPanel
from ..domain.v2_base import CapabilityStatus
from ..errors import DataQualityError
from ..services.identifiers import iso_utc, stable_id
from ..services.model_bindings import MODEL_BINDINGS
from ..services.qualification import qualify_models, validation_summary
from ..services.tabular import target_rows
from ..services.targets import build_target_registry
from ..services.temporal_evaluation import build_evaluation_plan
from ..services.training_pipeline import train_spec


def m01(payload: dict[str, Any], *, as_of_time=None) -> HandlerOutcome:
    bundle = _mapping(payload, "p5_offline_training_outcome_bundle")
    raw_count = len(bundle.get("records", []))
    targets = target_rows(bundle, training_cutoff=as_of_time)
    observed = sorted({(row["target_id"], row["horizon"], row["unit"]) for row in targets})
    definitions = build_target_registry(observed)
    target_panel = {"records": [_serialize_target(row) for row in targets]}
    registry = {
        "schema_version": "2.0.0",
        "records": [row.model_dump(mode="json") for row in definitions],
        "canonical_target_count": 17,
        "observed_target_count": len(observed),
    }
    manifest = _training_manifest(targets, definitions)
    confirmations = _confirmation_mapping(
        payload.get("p5_hypothesis_confirmation_registry", {}).get("records", []),
        registry["records"],
    )
    confirmation_mapping = {"records": confirmations}
    if not confirmations:
        confirmation_mapping.update({
            "availability": "UNAVAILABLE",
            "reason_code": "P5_HYPOTHESIS_CONFIRMATION_UNAVAILABLE",
        })
    return HandlerOutcome(
        values=(target_panel, registry, manifest, confirmation_mapping),
        diagnostics={"excluded_future_outcomes": raw_count - len(targets)},
    )


def m02(payload: dict[str, Any]) -> HandlerOutcome:
    records = _mapping(payload, "training_target_panel").get("records", [])
    fold_config = payload.get("representation_fold_plan")
    window_type = "EXPANDING"
    if isinstance(fold_config, dict):
        window_type = str(fold_config.get("window_type", window_type))
    plan, receipt = build_evaluation_plan(records, window_type=window_type)
    return HandlerOutcome(values=(plan, receipt))


def m03(payload: dict[str, Any]) -> HandlerOutcome:
    views = {
        row["view_id"]: row
        for row in _mapping(payload, "authorized_consumer_view_registry").get("views", [])
    }
    definitions = _mapping(payload, "target_definition_registry").get("records", [])
    specs: list[dict[str, Any]] = []
    binding_rows: list[dict[str, Any]] = []
    for target in definitions:
        if target.get("availability_status") != CapabilityStatus.AVAILABLE.value:
            continue
        for binding in MODEL_BINDINGS:
            binding_data = binding.model_dump(mode="json")
            spec, reason_code = _resolver_spec_decision(target, binding_data, views)
            if spec is None:
                binding_rows.append(_binding_rejection_row(target, binding_data, reason_code))
                continue
            specs.append(spec)
            binding_rows.append(_binding_row(spec, binding_data))
    if not specs:
        raise DataQualityError("no compatible resolver specification can be created")
    bias = {"records": [_bias_profile(row) for row in specs]}
    registry = {
        "schema_version": "2.0.0",
        "records": specs,
        "declarative_binding_source": "services.model_bindings.MODEL_BINDINGS",
    }
    return HandlerOutcome(values=(registry, bias, {"records": binding_rows}))


def m04(payload: dict[str, Any], *, seed: int) -> HandlerOutcome:
    views = {
        row["view_id"]: row
        for row in _mapping(payload, "authorized_consumer_view_registry").get("views", [])
    }
    targets = target_rows(_mapping(payload, "training_target_panel"))
    plan = _mapping(payload, "temporal_evaluation_plan")
    trained: list[dict[str, Any]] = []
    observations = []
    runs: list[dict[str, Any]] = []
    for spec in _mapping(payload, "resolver_spec_registry").get("records", []):
        view = views.get(spec["feature_view_id"])
        if view is None:
            runs.append({
                "resolver_id": spec["resolver_id"],
                "status": "SKIPPED_MISSING_VIEW",
                "reason_code": "P5_CONSUMER_VIEW_UNAVAILABLE",
                "view_id": spec["feature_view_id"],
            })
            continue
        model, model_observations, model_runs = train_spec(spec, view, targets, plan, seed)
        trained.append(model)
        observations.extend(model_observations)
        runs.extend(model_runs)
    if not trained or not observations:
        raise DataQualityError("training produced no models or OOF observations")
    oof_panel = OOFValidationObservationPanel(records=tuple(observations))
    validation = validation_summary(oof_panel)
    run_report = {
        "records": runs,
        "rolling_refits": True,
        "sealed_test_used": False,
        "run_count": len(runs),
    }
    return HandlerOutcome(values=(
        {"records": trained},
        run_report,
        validation,
        _representation_ablation(validation, trained),
        oof_panel,
    ))


def m05(payload: dict[str, Any]) -> HandlerOutcome:
    trained = _mapping(payload, "trained_resolver_registry").get("records", [])
    validation = _mapping(payload, "resolver_validation_result_panel").get("records", [])
    accepted, rejected, promotion = qualify_models(trained, validation)
    rejection = {
        "status": "EMPTY" if not rejected else "HAS_REJECTIONS",
        "records": rejected,
    }
    confirmation = {
        "records": [
            {
                "resolver_id": row["resolver_id"],
                "classification": row["qualification"],
                "development_only": True,
                "test_holdout_status": "SEALED",
            }
            for row in accepted
        ],
        "status": "MULTIFOLD_DEVELOPMENT_ONLY_TEST_HOLDOUT_SEALED",
    }
    return HandlerOutcome(values=(
        {"records": accepted, "qualification_version": "P5-RC34-W2-V2"},
        rejection,
        {"records": promotion, "multiple_testing_policy": "HOLM_STEP_DOWN"},
        confirmation,
    ))


def _resolver_spec(target, binding, views):
    spec, _ = _resolver_spec_decision(target, binding, views)
    return spec


def _resolver_spec_decision(target, binding, views):
    if binding["capability_status"] != CapabilityStatus.AVAILABLE.value:
        return None, "P5_CAPABILITY_UNAVAILABLE"
    if target["target_family"] not in binding["target_families"]:
        return None, "P5_TARGET_FAMILY_UNSUPPORTED"
    view_id = next((name for name in binding["compatible_views"] if name in views), None)
    if view_id is None:
        return None, "P5_CONSUMER_VIEW_UNAVAILABLE"
    resolver_id = stable_id(
        "resolver", binding["binding_id"], target["target_id"], target["horizon"], view_id,
    )
    return {
        "resolver_id": f"{binding['resolver_family'].lower()}-{resolver_id}",
        "resolver_family": binding["resolver_family"],
        "implementation_id": binding["implementation_id"],
        "binding_id": binding["binding_id"],
        "target_id": target["target_id"],
        "target_family": target["target_family"],
        "horizon": target["horizon"],
        "unit": target["units"],
        "feature_view_id": view_id,
        "required_features": binding["required_features"],
        "optional_features": binding["optional_features"],
        "minimum_sample": binding["minimum_sample"],
        "resource_budget": binding["resource_budget"],
        "parameters": binding["parameters"],
        "role": binding["role"],
    }, None


def _binding_rejection_row(target, binding, reason_code):
    return {
        "resolver_id": None,
        "binding_id": binding["binding_id"],
        "view_id": None,
        "target_id": target["target_id"],
        "horizon": target["horizon"],
        "decision": "REJECTED",
        "reason_code": reason_code,
        "required_features": binding["required_features"],
        "optional_features": binding["optional_features"],
        "capability_status": binding["capability_status"],
    }


def _binding_row(spec, binding):
    return {
        "resolver_id": spec["resolver_id"],
        "binding_id": binding["binding_id"],
        "view_id": spec["feature_view_id"],
        "required_features": binding["required_features"],
        "optional_features": binding["optional_features"],
        "capability_status": binding["capability_status"],
        "decision": "ACCEPTED",
        "reason_code": None,
    }


def _training_manifest(targets, definitions):
    available = [
        row.target_id for row in definitions
        if row.availability_status is CapabilityStatus.AVAILABLE
    ]
    return {
        "record_count": len(targets),
        "start_time": iso_utc(targets[0]["prediction_timestamp"]),
        "end_time": iso_utc(targets[-1]["prediction_timestamp"]),
        "outcome_available_end_time": iso_utc(max(row["available_at"] for row in targets)),
        "observed_target_ids": sorted(set(available)),
        "test_selection_allowed": False,
    }


def _confirmation_mapping(passports, targets):
    output: list[dict[str, Any]] = []
    for passport in passports:
        if passport.get("status") != "APPROVED" or int(passport.get("remaining_budget", 0)) <= 0:
            continue
        allowed_targets = set(passport.get("allowed_targets", []))
        allowed_horizons = set(passport.get("allowed_horizons", []))
        for target in targets:
            if target.get("availability_status") != CapabilityStatus.AVAILABLE.value:
                continue
            if target["target_id"] in allowed_targets and target["horizon"] in allowed_horizons:
                output.append({
                    "hypothesis_id": passport["hypothesis_id"],
                    "target_id": target["target_id"],
                    "horizon": target["horizon"],
                    "confirmation_type": "CONFIRMATORY",
                })
    return output


def _representation_ablation(validation, trained):
    metrics = {row["resolver_id"]: row["mse"] for row in validation["records"]}
    by_view: dict[str, list[float]] = defaultdict(list)
    for model in trained:
        if model["resolver_id"] in metrics:
            by_view[model["feature_view_id"]].append(metrics[model["resolver_id"]])
    return {
        "records": [
            {
                "view_id": view,
                "mean_multifold_validation_mse": float(np.mean(values)),
                "sealed_test_used": False,
            }
            for view, values in sorted(by_view.items())
        ]
    }


def _bias_profile(spec):
    return {
        "resolver_id": spec["resolver_id"],
        "resolver_family": spec["resolver_family"],
        "functional_form": spec["resolver_family"],
        "cross_asset": False,
        "tail_awareness": "MEDIUM" if spec["target_family"] == "TAIL" else "LOW",
        "interpretability": "HIGH" if spec["resolver_family"] in {"BASELINE", "LINEAR"} else "MEDIUM",
    }


def _serialize_target(row):
    return {
        **row,
        "prediction_timestamp": row["prediction_timestamp"].isoformat(),
        "label_end_time": row["label_end_time"].isoformat(),
        "available_at": row["available_at"].isoformat(),
    }


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
