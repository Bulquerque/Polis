"""S9: strong V2 publication, compact V1 projection and lineage closure."""
from __future__ import annotations

from typing import Any

from ..domain.core import HandlerOutcome, ModuleStatus
from ..domain.forecast import EnsembleForecastPanel, ForecastMemberPanel
from ..errors import DataQualityError
from ..services import publication


def m01(payload: dict[str, Any]) -> HandlerOutcome:
    calibrated = ForecastMemberPanel.model_validate(_mapping(payload, "calibrated_forecast_member_panel"))
    result = publication.member_panel(
        calibrated,
        _mapping(payload, "resolver_diversity_panel"),
        _mapping(payload, "resolver_bias_registry"),
        _mapping(payload, "resolver_view_binding_registry"),
        _mapping(payload, "cross_phase_research_lineage_map"),
    )
    unmapped = [row["record_id"] for row in result["records"] if row["critical_lineage_status"] == "UNMAPPED"]
    if unmapped:
        raise DataQualityError(f"critical forecast member lineage is unmapped: {unmapped[:5]}")
    return HandlerOutcome(values=(result,))


def m02(payload: dict[str, Any], *, run_id: str, cycle_id: str, decision_time: str, created_at: str) -> HandlerOutcome:
    panel = EnsembleForecastPanel.model_validate(_mapping(payload, "ensemble_forecast_panel"))
    values = publication.v2_distribution_and_scenarios(
        panel,
        _mapping(payload, "validated_tail_scenario_registry"),
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        created_at=created_at,
        confidence_panel=payload.get("forecast_confidence_panel"),
        context_panel=payload.get("resolver_context_router_panel"),
    )
    unavailable = _unavailable_capabilities(values[:3])
    if unavailable:
        return HandlerOutcome(
            values=values,
            status=ModuleStatus.DEGRADED,
            warnings=(f"optional V2 capabilities unavailable: {', '.join(unavailable)}",),
        )
    return HandlerOutcome(values=values)


def m03(
    payload: dict[str, Any],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
) -> HandlerOutcome:
    values = publication.v2_context_publication(
        payload,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        created_at=created_at,
    )
    unavailable = _unavailable_capabilities(values)
    if unavailable:
        return HandlerOutcome(
            values=values,
            status=ModuleStatus.DEGRADED,
            warnings=(f"context capabilities unavailable: {', '.join(unavailable)}",),
        )
    return HandlerOutcome(values=values)


def m04(payload: dict[str, Any]) -> HandlerOutcome:
    panel = EnsembleForecastPanel.model_validate(_mapping(payload, "ensemble_forecast_panel"))
    return HandlerOutcome(values=(publication.compact_panel(panel),))


def m05(
    payload: dict[str, Any],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
    output_references: dict[str, Any],
) -> HandlerOutcome:
    return HandlerOutcome(values=publication.handoffs(
        created_at=created_at,
        output_references=output_references,
        forecast_member_panel=_mapping(payload, "forecast_member_panel"),
        ensemble_selection_report=_mapping(payload, "ensemble_selection_report"),
        representation_ablation_report=_mapping(payload, "representation_downstream_ablation_report"),
        market_belief_state=payload.get("market_belief_state"),
        ambiguity_set=payload.get("ambiguity_set"),
        forecast_distribution_panel=payload.get("forecast_distribution_panel"),
        forecast_scenario_panel=payload.get("forecast_scenario_panel"),
        published_covariance_registry=payload.get("published_covariance_registry"),
        published_regime_ood_state=payload.get("published_regime_ood_surprise_panel"),
        forecast_confidence_panel=payload.get("forecast_confidence_panel"),
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
    ))


def _unavailable_capabilities(values: tuple[dict[str, Any], ...]) -> list[str]:
    unavailable = []
    for value in values:
        for name, item in value.items():
            if isinstance(item, dict) and item.get("availability") == "UNAVAILABLE":
                unavailable.append(str(name))
        if value.get("availability") == "UNAVAILABLE":
            unavailable.append(str(value.get("artifact_type", "artifact")))
    return sorted(set(unavailable))


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
