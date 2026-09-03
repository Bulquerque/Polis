"""Canonical content-addressed P5 V2 handoff construction."""
from __future__ import annotations

from typing import Any

from ..boundary.models import canonical_sha256
from ..domain.v2_publication import Phase6StrategyScenarioManifest
from ..errors import DataQualityError
from .v2_artifacts import artifact_reference, identity_fields
from .v2_context_publication import build_confidence_artifact


def build_v2_handoff(
    *,
    forecast_distribution_panel: dict[str, Any],
    forecast_scenario_panel: dict[str, Any],
    ambiguity_set: dict[str, Any],
    market_belief_state: dict[str, Any],
    published_covariance_registry: dict[str, Any],
    published_regime_ood_state: dict[str, Any],
    forecast_confidence_panel: dict[str, Any],
    forecast_member_panel: dict[str, Any],
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = (run_id, cycle_id, decision_time, created_at)
    artifacts = _artifact_bundle(
        forecast_distribution_panel, forecast_scenario_panel, ambiguity_set,
        market_belief_state, published_covariance_registry, published_regime_ood_state,
        forecast_confidence_panel, forecast_member_panel, runtime,
    )
    references = {
        name: artifact_reference(name, artifact, row_count=_row_count(artifact))
        for name, artifact in artifacts.items()
    }
    capabilities = _capabilities(artifacts)
    manifest = _manifest(references, artifacts, capabilities, runtime)
    return manifest.model_dump(mode="json"), artifacts


def _artifact_bundle(distributions, scenarios, ambiguity, belief, covariance, regime, confidence_panel, members, runtime):
    run_id, cycle_id, decision_time, created_at = runtime
    confidence = build_confidence_artifact(
        confidence_panel, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
    )
    artifacts = {
        "market_belief_state": _envelope("market_belief_state", belief, "P5.S9.M05", *runtime),
        "return_distributions": _nested(distributions, "return_distributions"),
        "volatility_distributions": _nested(distributions, "volatility_distributions"),
        "path_risk_forecasts": _nested(distributions, "path_risk_forecasts"),
        "scenario_paths": _nested(scenarios), "ambiguity_sets": _nested(ambiguity),
        "dependence_states": _nested(covariance), "regime_ood_states": _nested(regime),
        "forecast_confidence": _nested(confidence),
    }
    artifacts["availability_report"] = _availability_report(artifacts, *runtime)
    artifacts["lineage_report"] = _lineage_report(artifacts, members, *runtime)
    return artifacts


def _manifest(references, artifacts, capabilities, runtime):
    run_id, cycle_id, decision_time, created_at = runtime
    published_artifacts = tuple(references)
    handoff_mode = _handoff_mode(artifacts)
    payload = {
        "references": {name: ref.model_dump(mode="json") for name, ref in references.items()},
        **capabilities,
        "producer_contract_version": "P5-P6-V2",
        "handoff_mode": handoff_mode,
        "published_artifacts": published_artifacts,
        "published_capabilities": capabilities,
    }
    identity = identity_fields(
        module_id="P5.S9.M05", run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at, payload=payload,
        lineage_inputs=[artifact["lineage_id"] for artifact in artifacts.values()],
    )
    return Phase6StrategyScenarioManifest(
        **identity,
        market_belief_state=references["market_belief_state"],
        return_distributions=references["return_distributions"],
        volatility_distributions=references["volatility_distributions"],
        path_risk_forecasts=references["path_risk_forecasts"],
        scenario_paths=references["scenario_paths"], ambiguity_sets=references["ambiguity_sets"],
        dependence_states=references["dependence_states"], regime_ood_states=references["regime_ood_states"],
        forecast_confidence=references["forecast_confidence"],
        availability_report=references["availability_report"], lineage_report=references["lineage_report"],
        producer_contract_version="P5-P6-V2",
        handoff_mode=handoff_mode,
        published_artifacts=published_artifacts,
        published_capabilities=capabilities,
        **capabilities,
        production_promotion_allowed=False,
    )


def _nested(container: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    value = container.get(name) if name else container
    if not isinstance(value, dict):
        raise DataQualityError(f"V2 handoff artifact {name or 'root'} is missing")
    artifact = value.get("artifact") if isinstance(value.get("artifact"), dict) else value
    required = {"artifact_id", "artifact_sha256", "producer_module_id", "lineage_id"}
    if not required.issubset(artifact):
        raise DataQualityError(f"V2 handoff artifact {name or 'root'} lacks identity fields")
    return artifact


def _envelope(name, content, module_id, run_id, cycle_id, decision_time, created_at):
    payload = {"artifact_type": name, "content": content}
    identity = identity_fields(
        module_id=module_id, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=payload, lineage_inputs=(name, content.get("schema_version"), content.get("record_count")),
    )
    serialized = {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in identity.items()}
    envelope = {**serialized, **payload}
    records = content.get("records") if isinstance(content, dict) else None
    if isinstance(records, list):
        envelope["records"] = records
        envelope["record_count"] = len(records)
        envelope["content_sha256"] = canonical_sha256(records)
    return envelope


def _availability_report(artifacts, run_id, cycle_id, decision_time, created_at):
    records = [{
        "artifact_type": name,
        "artifact_id": artifact["artifact_id"],
        "availability": _artifact_availability(artifact),
        "reason_code": artifact.get("reason_code"),
    } for name, artifact in sorted(artifacts.items())]
    return _envelope("availability_report", {"records": records}, "P5.S9.M05", run_id, cycle_id, decision_time, created_at)


def _lineage_report(artifacts, members, run_id, cycle_id, decision_time, created_at):
    records = [{
        "artifact_type": name,
        "artifact_id": artifact["artifact_id"],
        "lineage_id": artifact["lineage_id"],
        "producer_module_id": artifact["producer_module_id"],
    } for name, artifact in sorted(artifacts.items())]
    member_lineage = [{
        "record_id": row.get("record_id"), "resolver_id": row.get("resolver_id"),
        "lineage_id": row.get("lineage_id"), "critical_lineage_status": row.get("critical_lineage_status"),
    } for row in members.get("records", [])]
    return _envelope("lineage_report", {"artifacts": records, "members": member_lineage}, "P5.S9.M05", run_id, cycle_id, decision_time, created_at)


def _capabilities(artifacts):
    belief_content = artifacts["market_belief_state"].get("content", {})
    belief_rows = belief_content.get("records", [])
    scenario = _aggregate_capability(belief_rows, "scenario_capability", empty="UNAVAILABLE")
    ambiguity = _aggregate_capability(belief_rows, "ambiguity_capability", empty="UNAVAILABLE")
    surface = _aggregate_capability(belief_rows, "surface_capability", empty="UNAVAILABLE")
    extended_scenario = _artifact_capability(artifacts["scenario_paths"], unavailable="UNAVAILABLE")
    extended_ambiguity = _artifact_capability(artifacts["ambiguity_sets"], unavailable="UNAVAILABLE")
    return {
        "scenario_capability": scenario,
        "surface_capability": surface,
        "ambiguity_capability": ambiguity,
        "extended_scenario_path_capability": extended_scenario,
        "extended_ambiguity_capability": extended_ambiguity,
    }


def _handoff_mode(artifacts: dict[str, dict[str, Any]]) -> str:
    required = (
        "market_belief_state", "return_distributions", "volatility_distributions",
        "path_risk_forecasts", "scenario_paths", "ambiguity_sets",
        "dependence_states", "regime_ood_states", "forecast_confidence",
    )
    return (
        "FULL_V2"
        if all(_artifact_availability(artifacts[name]) in {"AVAILABLE", "DEGRADED"} for name in required)
        else "DEGRADED_V2"
    )


def _aggregate_capability(rows, field, *, empty):
    values = [str(row.get(field, "UNAVAILABLE")) for row in rows]
    if not values:
        return empty
    if all(value == "AVAILABLE" for value in values):
        return "AVAILABLE"
    if any(value in {"AVAILABLE", "LIMITED"} for value in values):
        return "LIMITED"
    return "UNAVAILABLE"


def _artifact_capability(artifact, *, unavailable):
    return "AVAILABLE" if _artifact_availability(artifact) in {"AVAILABLE", "DEGRADED"} else unavailable


def _artifact_availability(artifact):
    explicit = artifact.get("availability")
    if explicit is not None:
        return str(explicit)
    records = artifact.get("records")
    if not isinstance(records, list):
        content = artifact.get("content", {})
        records = content.get("records") if isinstance(content, dict) else None
    if not isinstance(records, list) or not records:
        return "UNAVAILABLE"
    states = {str(row.get("validity_status")) for row in records if row.get("validity_status") is not None}
    return "DEGRADED" if "DEGRADED" in states else "AVAILABLE"


def _row_count(artifact):
    if isinstance(artifact.get("records"), list):
        return len(artifact["records"])
    content = artifact.get("content", {})
    if isinstance(content.get("records"), list):
        return len(content["records"])
    return None
