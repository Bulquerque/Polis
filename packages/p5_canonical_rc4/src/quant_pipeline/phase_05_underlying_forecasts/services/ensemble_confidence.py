"""Evidence-only confidence components for probabilistic ensembles."""
from __future__ import annotations

from math import exp
from typing import Any

import numpy as np

from ..errors import DataQualityError


def confidence_components(members, score_rows, weights, dispersion, context, *, resolver_key, effective_count):
    sample_quality = min(1.0, min(score_rows[resolver_key(row)]["sample_size"] for row in members) / 40.0)
    coverage = min(_coverage_quality(score_rows[resolver_key(row)].get("coverage_90")) for row in members)
    pit = min(_pit_quality(score_rows[resolver_key(row)].get("pit_ks_pvalue")) for row in members)
    scale = max(float(np.average(np.abs([row.point_forecast for row in members]), weights=weights)), 1e-4)
    return {
        "calibration_component": float(np.clip(0.5 * coverage + 0.5 * pit, 0.0, 1.0)),
        "data_quality_component": sample_quality,
        "model_stability_component": float(np.clip(effective_count(weights) / max(1.0, len(members)), 0.0, 1.0)),
        "ensemble_disagreement_component": float(np.clip(exp(-dispersion / scale), 0.0, 1.0)),
        "ood_component": _complement_optional(context, "ood"),
        "regime_uncertainty_component": _complement_optional(context, "regime_uncertainty"),
    }


def confidence_record(row, selection, *, effective_count):
    components = selection["confidence_components"]
    status = "CALIBRATED" if selection["confidence_evidence_fraction"] == 1.0 else "PARTIALLY_CALIBRATED"
    return {
        "record_id": row.record_id,
        "underlying": row.underlying,
        "target_id": row.target_id,
        "horizon": row.horizon,
        **components,
        "overall_confidence": row.confidence,
        "confidence": row.confidence,
        "confidence_method": "GEOMETRIC_MEAN_OF_OOS_COMPONENTS_WITH_EVIDENCE_FRACTION",
        "calibration_version": "RC34-CONFIDENCE-V3",
        "calibration_status": status,
        "abstained": row.abstained,
        "epistemic_uncertainty": row.epistemic_uncertainty,
        "effective_ensemble_size": effective_count(np.asarray(row.weights)),
        "lineage_id": row.lineage_id,
    }


def _coverage_quality(value: Any) -> float:
    if value is None:
        raise DataQualityError("confidence requires interval coverage evidence")
    return float(np.clip(1.0 - abs(float(value) - 0.90) / 0.90, 0.0, 1.0))


def _pit_quality(value: Any) -> float:
    if value is None:
        raise DataQualityError("confidence requires PIT evidence")
    return float(np.clip(float(value) / 0.10, 0.0, 1.0))


def _complement_optional(context: dict[str, Any], name: str) -> float | None:
    value = context.get("context_components", {}).get(name)
    if value is None:
        return None
    number = float(value)
    if not np.isfinite(number) or not 0.0 <= number <= 1.0:
        raise DataQualityError(f"context component {name} must be finite and bounded")
    return 1.0 - number
