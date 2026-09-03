"""Publication services for validated P5 artifacts and downstream handoffs."""
from __future__ import annotations

from typing import Any

from ..domain.distributions import EmpiricalDistribution, ScenarioDistribution, point_value, quantile_value
from ..domain.forecast import EnsembleForecastPanel, ForecastMemberPanel
from .v2_context_publication import build_dependence_artifact, build_regime_ood_artifact
from .v2_marginal_publication import build_marginal_artifacts
from .v2_scenario_publication import build_scenario_artifacts



def member_panel(
    calibrated: ForecastMemberPanel,
    diversity: dict[str, Any],
    bias_registry: dict[str, Any],
    view_registry: dict[str, Any],
    lineage_map: dict[str, Any],
) -> dict[str, Any]:
    records = []
    for record in calibrated.records:
        research = lineage_map.get("resolver_lineage", {}).get(record.resolver_id)
        if research is None:
            research = {
                "resolver_id": record.resolver_id,
                "status": "MAPPED_RUNTIME_FORECAST_LINEAGE",
                "source": "FORECAST_MEMBER_RECORD",
                "forecast_lineage_id": record.lineage_id,
            }
        records.append({
            **record.model_dump(mode="json"),
            "bias_profile": _lookup(bias_registry, record.resolver_id) or {
                "resolver_id": record.resolver_id,
                "status": "NOT_REGISTERED",
                "source": "RUNTIME_BUILTIN_OR_ROLLING_STATE",
            },
            "view_binding": _lookup(view_registry, record.resolver_id) or {
                "resolver_id": record.resolver_id,
                "view_id": record.feature_view_id,
                "status": "DERIVED_FROM_FORECAST_RECORD",
            },
            "diversity": _diversity(diversity, record.record_id) or {
                "record_id": record.record_id,
                "status": "NOT_SELECTED_OR_SINGLE_MEMBER",
            },
            "research_lineage": research,
            "critical_lineage_status": "MAPPED" if research.get("status") != "UNMAPPED" else "UNMAPPED",
        })
    return {"records": records, "record_count": len(records)}


def distribution_and_scenarios(
    panel: EnsembleForecastPanel,
    validated_tail_registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    distributions = {"records": [_distribution_row(row) for row in panel.records]}
    scenario_rows = [payload for row in panel.records if (payload := _scenario_payload_from_ensemble(row)) is not None]
    seen = {str(row["record_id"]) for row in scenario_rows}
    scenario_rows.extend(_tail_scenario_rows(validated_tail_registry, seen))
    return distributions, {
        "availability": "AVAILABLE" if scenario_rows else "UNAVAILABLE",
        "records": scenario_rows,
        "validation_passed": bool(validated_tail_registry.get("validated")),
        "probabilistic_and_stress_separated": True,
    }


def v2_distribution_and_scenarios(
    panel: EnsembleForecastPanel,
    validated_tail_registry: dict[str, Any],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
    confidence_panel: dict[str, Any] | None = None,
    context_panel: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    legacy_distributions, legacy_scenarios = distribution_and_scenarios(panel, validated_tail_registry)
    marginals = build_marginal_artifacts(
        panel, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        confidence_panel=confidence_panel,
    )
    scenarios, ambiguity = build_scenario_artifacts(
        validated_tail_registry, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        confidence_panel=confidence_panel, context_panel=context_panel,
    )
    distributions = {
        "schema_version": "P5-MARGINAL-BUNDLE-V2",
        **marginals,
        "legacy_distribution_records": legacy_distributions["records"],
    }
    scenarios["legacy_records"] = legacy_scenarios["records"]
    legacy_ambiguity = build_ambiguity_set(legacy_scenarios, confidence_panel, context_panel)
    ambiguity["legacy_projection"] = legacy_ambiguity
    belief = build_market_belief_state(
        panel, legacy_scenarios, legacy_ambiguity, context_panel,
        decision_time=decision_time,
        confidence_panel=confidence_panel,
    )
    return distributions, scenarios, ambiguity, belief


def v2_context_publication(
    payload: dict[str, Any],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dependence = build_dependence_artifact(
        payload.get("covariance_forecast_registry"), run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
    )
    dependence["raw_registry"] = payload.get("covariance_forecast_registry") or {"availability": "UNAVAILABLE"}
    context = build_regime_ood_artifact(
        payload.get("regime_probability_member_panel"), payload.get("structural_break_member_panel"),
        payload.get("ood_drift_diagnostics_panel"), payload.get("regime_ood_surprise_panel"),
        run_id=run_id, cycle_id=cycle_id, decision_time=decision_time, created_at=created_at,
    )
    context["raw_context"] = payload.get("regime_ood_surprise_panel") or {"availability": "UNAVAILABLE"}
    context["router_policy"] = payload.get("resolver_context_router_panel") or {"availability": "UNAVAILABLE"}
    return dependence, context


def _distribution_row(row: Any) -> dict[str, Any]:
    return {
        "record_id": row.record_id,
        "as_of_time": row.as_of_time.isoformat(),
        "prediction_timestamp": row.prediction_timestamp.isoformat(),
        "underlying": row.underlying,
        "target_id": row.target_id,
        "horizon": row.horizon,
        "unit": row.unit,
        "distribution": row.distribution.model_dump(mode="json"),
        "confidence": row.confidence,
        "abstained": row.abstained,
        "lineage_id": row.lineage_id,
    }


def _tail_scenario_rows(registry: dict[str, Any], seen: set[str]) -> list[dict[str, Any]]:
    rows = []
    for raw in registry.get("records", []):
        distribution = raw.get("distribution", {})
        record_id = str(raw.get("record_id", ""))
        if distribution.get("kind") not in {"SCENARIOS", "EMPIRICAL"} or not record_id or record_id in seen:
            continue
        payload = {
            "record_id": record_id, "as_of_time": raw.get("as_of_time"),
            "prediction_timestamp": raw.get("prediction_timestamp"),
            "underlying": raw.get("underlying"), "target_id": raw.get("target_id"),
            "horizon": raw.get("horizon"), "unit": raw.get("unit"),
            "distribution": distribution, "lineage_id": raw.get("lineage_id"),
            "source": "VALIDATED_TAIL_SCENARIO_REGISTRY",
            "scenario_semantics": scenario_semantics(str(raw.get("unit", ""))),
        }
        payload["scenarios" if distribution.get("kind") == "SCENARIOS" else "samples"] = distribution.get("scenarios" if distribution.get("kind") == "SCENARIOS" else "samples", [])
        rows.append(payload); seen.add(record_id)
    return rows


def publish_context(
    covariance: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    covariance_output = dict(covariance or {"availability": "UNAVAILABLE", "records": []})
    context_output = dict(context or {"availability": "UNAVAILABLE", "records": []})
    covariance_output.setdefault("availability", "AVAILABLE" if covariance_output.get("records") else "UNAVAILABLE")
    context_output.setdefault("availability", "AVAILABLE" if context_output.get("records") else "UNAVAILABLE")
    return covariance_output, context_output

def _scenario_payload_from_ensemble(row: Any) -> dict[str, Any] | None:
    distribution = row.distribution
    base = {
        "record_id": row.record_id,
        "as_of_time": row.as_of_time.isoformat(),
        "prediction_timestamp": row.prediction_timestamp.isoformat(),
        "underlying": row.underlying,
        "target_id": row.target_id,
        "horizon": row.horizon,
        "unit": row.unit,
        "lineage_id": row.lineage_id,
        "source": "ENSEMBLE",
        "scenario_semantics": scenario_semantics(row.unit),
    }
    if isinstance(distribution, ScenarioDistribution):
        return {**base, "scenarios": distribution.model_dump(mode="json")["scenarios"]}
    if isinstance(distribution, EmpiricalDistribution):
        return {**base, "samples": list(distribution.samples), "distribution": distribution.model_dump(mode="json")}
    return None
def _lookup(registry: dict[str, Any], resolver_id: str) -> Any:
    for row in registry.get("records", []):
        if row.get("resolver_id") == resolver_id:
            return row
    return None


def _diversity(panel: dict[str, Any], record_id: str) -> Any:
    for row in panel.get("records", []):
        if record_id in row.get("candidate_ids", []):
            return row
    return None

from .downstream import build_ambiguity_set, build_market_belief_state, compact_panel, handoffs, scenario_semantics
