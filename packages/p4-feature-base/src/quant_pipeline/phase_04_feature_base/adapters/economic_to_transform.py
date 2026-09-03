from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..runtime.artifact_envelope import ArtifactEnvelope, RuntimeExecutionContext, build_artifact
from ..runtime.canonical import deterministic_id

_FAMILY_BY_PHENOMENON = {
    "momentum": "F01",
    "reversion": "F02",
    "fundamentals": "F03",
    "liquidity": "F04",
    "risk": "F05",
    "systemic_risk": "F06",
    "structure": "F06",
    "carry": "F07",
    "macro": "F08",
    "events": "F09",
    "narrative": "F10",
    "cross_phenomenon": "F11",
}


def _family_id(phenomenon: str) -> str:
    return _FAMILY_BY_PHENOMENON.get(phenomenon, f"F_{phenomenon.upper()}")


def _s7_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    attributes = raw.get("attributes") if isinstance(raw.get("attributes"), Mapping) else {}
    phenomenon = str(raw.get("phenomenon_id") or "unknown")
    feature_kind = str(raw.get("feature_kind") or "PERSPECTIVE")
    parameterization = str(
        attributes.get("parameterization_id")
        or attributes.get("interaction_id")
        or attributes.get("group_id")
        or f"{raw.get('feature_id')}.derived"
    )
    perspective = str(
        attributes.get("perspective_id")
        or ("conflict_state" if feature_kind == "CONFLICT" else "derived_interaction")
    )
    modalities = raw.get("source_modalities") or attributes.get("source_modalities") or ()
    quality = "VALIDATED" if str(raw.get("quality_state")) == "PASS" else str(raw.get("quality_state"))
    return {
        "decision_time": raw["decision_time"],
        "entity_id": str(raw["entity_id"]),
        "feature_id": str(raw["feature_id"]),
        "feature_value": raw.get("value"),
        "family_id": _family_id(phenomenon),
        "perspective_id": perspective,
        "parameterization_id": parameterization,
        "horizon_group": str(raw["horizon_group"]),
        "available_at": raw.get("available_at") or raw["decision_time"],
        "quality_state": quality,
        "missingness_state": str(raw.get("missingness_state", "STRUCTURALLY_MISSING")),
        "lineage_id": str(raw.get("record_lineage_id") or raw.get("lineage_id") or ""),
        "source_modalities": tuple(str(item) for item in modalities),
        "implementation_tier": "FOUNDATIONAL" if attributes.get("hypothesis_id") else "CORE",
        "is_primary_parameterization": parameterization.casefold().endswith("primary")
        or feature_kind != "PERSPECTIVE",
        "compute_cost": 1.0 if feature_kind == "PERSPECTIVE" else 1.5 if feature_kind == "CONFLICT" else 2.0,
    }


def horizon_panel_for_s7(
    panel: Mapping[str, Any], *, context: RuntimeExecutionContext
) -> ArtifactEnvelope:
    """Convert the S6 economic panel into the canonical S7 artifact contract."""
    records = [_s7_record(raw) for raw in panel.get("records", []) if isinstance(raw, Mapping)]
    return build_artifact(
        artifact_name="horizon_feature_panel",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S6.M04",
        context=context,
        grain=("decision_time", "entity_id", "feature_id", "horizon_group"),
        records=records,
        lineage_id=str(panel.get("lineage_id") or deterministic_id("lineage-horizon", records, 28)),
        metadata={
            "source_artifact_id": panel.get("artifact_id"),
            "adapter": "economic_to_transform.v1",
            "temporal_rule": "available_at=max(parent.available_at)",
        },
        execution_status="DEGRADED" if str(panel.get("execution_status")) == "DEGRADED" else "PRODUCED",
        quality_status="DEGRADED" if str(panel.get("quality_status")) == "DEGRADED" else "VALIDATED",
    )
