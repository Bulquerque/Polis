from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..economic_models import CanonicalObservationPanel
from ..runtime.canonical import deterministic_id

_QUALITY = {
    "PASS": "PASS",
    "VALIDATED": "PASS",
    "DEGRADED": "DEGRADED",
    "BLOCKED": "BLOCKED",
    "QUALITY_BLOCKED": "BLOCKED",
}

_MODALITY = {
    "MARKET": "market",
    "MARKET_TRADE": "market",
    "BENCHMARK": "market",
    "MACRO_BR": "macro",
    "MACRO_US": "macro",
    "TERM_STRUCTURE": "macro",
    "OPTION_CONTRACT": "option",
    "OPTION_QUOTE": "option",
    "EVENT": "event",
    "CALENDAR": "calendar",
    "SOCIAL_FEATURE": "social",
    "EVIDENCE": "social",
    "DISAGREEMENT": "social",
    "CONTEXT_MEMORY": "social",
    "HYPOTHESIS": "social",
    "FUNDAMENTAL": "fundamental",
}

_FUNDAMENTAL_VARIABLES = {
    "fundamental.net_income": "fundamental.net_income_ttm",
    "fundamental.gross_profit": "fundamental.gross_profit_ttm",
    "fundamental.operating_income": "fundamental.operating_income_ttm",
    "fundamental.debt": "fundamental.total_debt",
    "fundamental.operating_cash_flow": "fundamental.operating_cash_flow_ttm",
}

_OPTION_VARIABLES = {
    "option_quote.bid": "option.bid",
    "option_quote.ask": "option.ask",
    "option_quote.last": "option.last_price",
    "option_quote.mid": "option.last_price",
    "option_quote.volume": "option.volume",
    "option_quote.open_interest": "option.open_interest",
    "option_quote.implied_volatility": "option.implied_volatility",
    "option_contract.open_interest": "option.open_interest",
}


def _typed_value(row: Mapping[str, Any]) -> Any:
    field = {
        "NUMBER": "value_number",
        "INTEGER": "value_integer",
        "BOOLEAN": "value_boolean",
        "STRING": "value_string",
        "JSON": "value_json",
    }.get(str(row.get("value_type", "NULL")))
    return row.get(field) if field else None


def _sibling_values(panel: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in panel.get("records", []):
        if not isinstance(row, Mapping):
            continue
        source_record_id = str(row.get("source_record_id") or "")
        if source_record_id:
            grouped.setdefault(source_record_id, {})[str(row.get("variable_id"))] = _typed_value(row)
    return grouped


def _project_semantics(
    row: Mapping[str, Any], value: Any, siblings: Mapping[str, Any]
) -> tuple[str, str, Any, dict[str, Any]]:
    raw_modality = str(row.get("source_modality") or "UNKNOWN")
    modality = _MODALITY.get(raw_modality, raw_modality.casefold())
    dimensions = dict(row.get("dimensions") or {})
    variable_id = str(row["variable_id"])
    projected = variable_id
    if raw_modality == "BENCHMARK" and variable_id.startswith("benchmark."):
        projected = "market." + variable_id.split(".", 1)[1]
    elif raw_modality in {"MACRO_BR", "MACRO_US"}:
        projected = str(dimensions.get("series_id") or variable_id)
    elif raw_modality == "TERM_STRUCTURE":
        field = variable_id.split(".", 1)[-1]
        curve_id = str(dimensions.get("curve_id") or "curve")
        tenor = str(dimensions.get("tenor") or "")
        projected = f"curve.{curve_id}.{tenor}.{field}".replace("..", ".").strip(".")
    elif raw_modality in {"OPTION_CONTRACT", "OPTION_QUOTE"}:
        projected = _OPTION_VARIABLES.get(variable_id, variable_id)
        dimensions["underlying_id"] = str(row.get("entity_id"))
        dimensions["expiration_date"] = dimensions.get("expiry") or dimensions.get("maturity")
    elif raw_modality == "FUNDAMENTAL":
        projected = _FUNDAMENTAL_VARIABLES.get(variable_id, variable_id)
    elif raw_modality == "SOCIAL_FEATURE" and variable_id == "social_feature.feature_value":
        name = str(dimensions.get("feature_name") or dimensions.get("social_feature_id") or "unknown")
        projected = f"social.feature.{name}"
    elif raw_modality == "DISAGREEMENT":
        projected = variable_id.replace("disagreement.", "agent.disagreement.", 1)
    elif raw_modality == "CONTEXT_MEMORY" and variable_id == "context_memory.feature_value":
        name = str(dimensions.get("context_memory_feature_id") or "state")
        projected = f"memory.feature.{name}"
    elif raw_modality == "EVIDENCE" and variable_id == "evidence.relation":
        relation = str(value or "").upper()
        projected = "evidence.relation_score"
        value = 1.0 if relation == "SUPPORTS" else -1.0 if relation in {"CONTRADICTS", "REFUTES"} else 0.0
    elif raw_modality == "HYPOTHESIS" and variable_id == "hypothesis.evidence_count":
        projected, value = "hypothesis.active", 1.0
    dimensions.update(
        {
            "source_quality_score": siblings.get("evidence.source_quality_score")
            or siblings.get("social_feature.source_quality_score")
            or siblings.get("hypothesis.source_quality_score"),
            "underlying_id": dimensions.get("underlying_id") or row.get("entity_id"),
        }
    )
    return modality, projected, value, dimensions


def _economic_record(row: Mapping[str, Any], siblings: Mapping[str, Any]) -> dict[str, Any]:
    value = _typed_value(row)
    modality, variable_id, value, dimensions = _project_semantics(row, value, siblings)
    entity_id = str(row["entity_id"])
    if str(row.get("source_modality")) == "BENCHMARK" and entity_id.startswith("benchmark:"):
        entity_id = entity_id.split(":", 1)[1]
    return {
        "decision_time": row["decision_time"],
        "entity_id": entity_id,
        "variable_id": variable_id,
        "value": value,
        "source_modality": modality,
        "available_at": row["available_at"],
        "quality_state": _QUALITY.get(str(row.get("quality_state", "DEGRADED")), "DEGRADED"),
        "missingness_state": str(row.get("missingness_state", "STRUCTURALLY_MISSING")),
        "record_lineage_id": str(row.get("source_lineage_id") or row.get("observation_id") or ""),
        "reference_time": row.get("reference_time"),
        "event_time": row.get("event_time"),
        "published_at": row.get("published_at"),
        "source_id": row.get("source_artifact_id") or row.get("source_record_id"),
        "unit": dimensions.get("unit") or dimensions.get("units"),
        "attributes": {
            **dimensions,
            "observation_id": row.get("observation_id"),
            "entity_type": row.get("entity_type"),
            "source_artifact_name": row.get("source_artifact_name"),
            "source_record_id": row.get("source_record_id"),
            "freshness_seconds": row.get("freshness_seconds"),
            "vintage_id": row.get("vintage_id"),
            "typed_value_type": row.get("value_type"),
        },
    }


def canonical_panel_for_economic(
    panel: Mapping[str, Any],
    *,
    run_id: str,
    cycle_id: str,
    as_of_time: datetime,
    created_at: datetime,
) -> dict[str, Any]:
    """Project the typed S2 store into the narrow numeric/economic contract."""
    siblings = _sibling_values(panel)
    records = [
        _economic_record(row, siblings.get(str(row.get("source_record_id") or ""), {}))
        for row in panel.get("records", [])
        if isinstance(row, Mapping)
    ]
    payload = {
        "artifact_id": str(panel.get("artifact_id") or deterministic_id("economic-canonical", records, 24)),
        "schema_version": str(panel.get("schema_version") or "p4.canonical.economic.v1"),
        "pipeline_version": str(panel.get("pipeline_version") or "V14.9-RC1"),
        "run_id": run_id,
        "cycle_id": cycle_id,
        "as_of_time": as_of_time,
        "created_at": created_at,
        "lineage_id": str(panel.get("lineage_id") or deterministic_id("lineage", records, 24)),
        "records": records,
    }
    return CanonicalObservationPanel.model_validate(payload).model_dump(mode="json")
