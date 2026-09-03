"""Wave 3 ambiguity, V2 belief, compact view, and downstream handoffs."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any


from ..domain.distributions import point_value, quantile_value
from ..domain.forecast import EnsembleForecastPanel, UnderlyingForecastPanel, UnderlyingForecastRecord
from ..errors import DataQualityError
from .handoff_v2 import build_v2_handoff
from .identifiers import stable_id
from .belief_publication import (
    build_ambiguity_set, build_market_belief_state, scenario_semantics,
    scenario_values_and_probabilities,
)

_VERSION = "0.34.1rc4"
_CONTRACT = "P5-RC34.1-CONTRACT-CLOSURE-RC4"


def compact_panel(panel: EnsembleForecastPanel) -> UnderlyingForecastPanel:
    return UnderlyingForecastPanel(records=tuple(
        UnderlyingForecastRecord(
            as_of_time=row.as_of_time,
            prediction_timestamp=row.prediction_timestamp,
            underlying=row.underlying,
            target_id=row.target_id,
            horizon=row.horizon,
            unit=row.unit,
            point_forecast=point_value(row.distribution),
            q05=quantile_value(row.distribution, 0.05),
            q50=quantile_value(row.distribution, 0.50),
            q95=quantile_value(row.distribution, 0.95),
            confidence=row.confidence,
            abstained=row.abstained,
            lineage_id=row.lineage_id,
        ) for row in panel.records
    ))


def handoffs(
    *,
    created_at: str,
    output_references: dict[str, Any],
    forecast_member_panel: dict[str, Any],
    ensemble_selection_report: dict[str, Any],
    representation_ablation_report: dict[str, Any],
    market_belief_state: dict[str, Any] | None = None,
    ambiguity_set: dict[str, Any] | None = None,
    forecast_distribution_panel: dict[str, Any] | None = None,
    forecast_scenario_panel: dict[str, Any] | None = None,
    published_covariance_registry: dict[str, Any] | None = None,
    published_regime_ood_state: dict[str, Any] | None = None,
    forecast_confidence_panel: dict[str, Any] | None = None,
    run_id: str | None = None,
    cycle_id: str | None = None,
    decision_time: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not output_references:
        raise DataQualityError("handoff requires output references")
    refs = _canonicalize(output_references)
    content = _manifest_content(refs, ensemble_selection_report, market_belief_state, ambiguity_set)
    manifest_id = stable_id("p5-output-handoff", content)
    output = _output_manifest(manifest_id, created_at, refs, ensemble_selection_report, content)
    strategy = _strategy_manifest(manifest_id, created_at, refs, market_belief_state, ambiguity_set)
    if all((run_id, cycle_id, decision_time, forecast_distribution_panel, forecast_scenario_panel,
            published_covariance_registry, published_regime_ood_state, forecast_confidence_panel,
            market_belief_state, ambiguity_set)):
        strategy, embedded = build_v2_handoff(
            forecast_distribution_panel=forecast_distribution_panel,
            forecast_scenario_panel=forecast_scenario_panel,
            ambiguity_set=ambiguity_set,
            market_belief_state=market_belief_state,
            published_covariance_registry=published_covariance_registry,
            published_regime_ood_state=published_regime_ood_state,
            forecast_confidence_panel=forecast_confidence_panel,
            forecast_member_panel=forecast_member_panel,
            run_id=run_id, cycle_id=cycle_id, decision_time=decision_time, created_at=created_at,
        )
        output["embedded_v2_artifacts"] = embedded
        output["phase6_strategy_scenario_manifest_id"] = strategy["artifact_id"]
        output["artifact_transport_mode"] = "EMBEDDED_WITH_CONTENT_ADDRESSED_REFERENCES"
        output["hash_scope"] = "FULL_MANIFEST_EXCLUDING_CONTENT_SHA256"
        output["content_sha256"] = _sha256({
            key: value for key, value in output.items() if key != "content_sha256"
        })
    return (
        output,
        _lineage_manifest(manifest_id, created_at, forecast_member_panel),
        _representation_manifest(manifest_id, created_at, representation_ablation_report),
        strategy,
    )


def _manifest_content(refs, selection, beliefs, ambiguity):
    return {
        "outputs": refs,
        "ensemble_selection": selection,
        "market_belief_state": beliefs or {"availability": "UNAVAILABLE"},
        "ambiguity_set": ambiguity or {"availability": "UNAVAILABLE"},
    }


def _output_manifest(manifest_id, created_at, refs, selection, content):
    return {
        "artifact_id": manifest_id,
        "phase_id": "P5",
        "contract_version": _CONTRACT,
        "pipeline_version": _VERSION,
        "created_at": created_at,
        "content_sha256": _sha256(content),
        "outputs": refs,
        "consumer_views": {
            "P6_V2": {
                "producer_contract": "P5-P6-V2",
                "handoff_mode": "FULL_V2_OR_EXPLICITLY_DEGRADED",
                "artifact_set": [
                    "market_belief_state", "return_distributions",
                    "volatility_distributions", "path_risk_forecasts",
                    "scenario_paths", "ambiguity_sets", "dependence_states",
                    "regime_ood_states", "forecast_confidence",
                    "availability_report", "lineage_report",
                ],
            },
            "P6_V1_ADAPTER": {"underlying_forecast_panel": "underlying_forecast_panel"},
            "P7": "P7_CONSUMES_P6_CANDIDATES_NOT_RAW_P5_FORECASTS",
        },
        "ensemble_selection": selection,
        "rules": [
            "compact_panel_does_not_replace_sidecars",
            "member_identity_must_survive",
            "abstention_must_be_preserved",
            "missing_price_anchor_never_becomes_synthetic_terminal_price",
            "stress_alternatives_are_not_empirical_probabilities",
        ],
    }


def _lineage_manifest(manifest_id, created_at, panel):
    fields = ("record_id", "as_of_time", "prediction_timestamp", "resolver_id", "target_id", "horizon", "model_artifact_id", "feature_view_id", "lineage_id", "critical_lineage_status")
    return {
        "artifact_id": stable_id("p5-resolver-lineage", manifest_id),
        "contract_version": _CONTRACT,
        "pipeline_version": _VERSION,
        "created_at": created_at,
        "members": [{name: row.get(name) for name in fields} for row in panel.get("records", [])],
    }


def _representation_manifest(manifest_id, created_at, report):
    return {
        "artifact_id": stable_id("p5-representation-lineage", manifest_id),
        "contract_version": _CONTRACT,
        "pipeline_version": _VERSION,
        "created_at": created_at,
        "representation_ablation": report,
        "feedback_route": "NEXT_CYCLE_ONLY",
    }


def _strategy_manifest(manifest_id, created_at, refs, beliefs, ambiguity):
    return {
        "artifact_id": stable_id("phase6-strategy-scenario-manifest", manifest_id),
        "contract_version": "P5-P6-V2",
        "pipeline_version": _VERSION,
        "created_at": created_at,
        "p5_handoff_manifest_id": manifest_id,
        "market_belief_state_available": bool((beliefs or {}).get("records")),
        "ambiguity_set_available": (ambiguity or {}).get("availability") == "AVAILABLE",
        "scenario_reference": refs.get("forecast_scenario_panel"),
        "confidence_reference": refs.get("forecast_confidence_panel"),
        "dependence_reference": refs.get("published_covariance_registry"),
        "regime_ood_reference": refs.get("published_regime_ood_surprise_panel"),
        "production_promotion_allowed": False,
    }


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict): return {str(key): _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)): return [_canonicalize(item) for item in value]
    if isinstance(value, datetime): return value.isoformat()
    return value


def _sha256(value: Any) -> str:
    encoded = json.dumps(_canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
