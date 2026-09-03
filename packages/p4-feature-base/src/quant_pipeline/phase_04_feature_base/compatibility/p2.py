from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..artifact_protocol import lineage_hash, stable_hash
from ..economic_errors import ContractError
from ..economic_models import CanonicalObservationPanel, ExecutionContext, MissingnessState, QualityState
from .policy import LegacyAdapterPolicy


def _records(artifact: Any) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    if isinstance(artifact, list):
        return [dict(row) for row in artifact]
    if isinstance(artifact, dict):
        for key in ("records", "rows", "items"):
            if isinstance(artifact.get(key), list):
                return [dict(row) for row in artifact[key]]
    raise ContractError("P4_S4_P2_ARTIFACT_INVALID", "P2 artifact must contain records")


def _time(
    value: Any,
    *,
    field_name: str,
    policy: LegacyAdapterPolicy,
    fallback: datetime,
) -> datetime:
    if value is None:
        if policy.allow_temporal_fallback:
            return fallback
        raise ContractError("P4_S4_P2_TIME_MISSING", f"missing required temporal field: {field_name}")
    text = str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed
    if len(text) == 10:
        return parsed.replace(tzinfo=timezone.utc)
    if policy.allow_naive_datetime_utc:
        return parsed.replace(tzinfo=timezone.utc)
    raise ContractError("P4_S4_P2_TIME_NAIVE", f"timezone required for field: {field_name}")


def _quality(value: Any) -> QualityState:
    text = str(value or "PASS").upper()
    if text in {"BLOCKED", "FAIL"}:
        return QualityState.BLOCKED
    return QualityState.DEGRADED if text not in {"PASS", "OK"} else QualityState.PASS


def _lineage(row: dict[str, Any], *, prefix: str, policy: LegacyAdapterPolicy) -> str:
    value = row.get("lineage_id")
    if value:
        return str(value)
    if policy.allow_generated_lineage:
        return f"{prefix}-{stable_hash(row)[:20]}"
    raise ContractError("P4_S4_P2_LINEAGE_MISSING", "P2 record is missing lineage_id")


def _missingness(quality: QualityState) -> MissingnessState:
    return MissingnessState.QUALITY_BLOCKED if quality is QualityState.BLOCKED else MissingnessState.OBSERVED


def _decision_and_available(
    row: dict[str, Any], context: ExecutionContext, policy: LegacyAdapterPolicy
) -> tuple[datetime, datetime, bool]:
    available = _time(
        row.get("available_at"), field_name="available_at", policy=policy, fallback=context.as_of_time
    )
    decision = _time(
        row.get("as_of_time") or row.get("as_of_date") or row.get("date"),
        field_name="as_of_time/as_of_date/date",
        policy=policy,
        fallback=available,
    )
    aligned = decision < available
    return (available if aligned else decision), available, aligned


def _append_market(
    output: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    context: ExecutionContext,
    policy: LegacyAdapterPolicy,
    role: str = "asset",
) -> None:
    mapping = {
        "open": "market.open",
        "high": "market.high",
        "low": "market.low",
        "close": "market.close",
        "volume": "market.volume",
        "financial_volume": "market.financial_volume",
        "bid": "market.bid",
        "ask": "market.ask",
        "reference_price_t": "market.reference_price",
        "liquidity_score": "market.liquidity_score",
        "cost_estimate": "market.cost_estimate",
        "shares_outstanding": "market.shares_outstanding",
    }
    for row in rows:
        decision, available, aligned = _decision_and_available(row, context, policy)
        entity = str(row.get("underlying") or row.get("entity_id") or row.get("benchmark_id") or "")
        if not entity:
            raise ContractError("P4_S4_P2_ENTITY_MISSING", "market record is missing entity identifier")
        quality = _quality(row.get("quality_flag"))
        lineage = _lineage(row, prefix="p2-market", policy=policy)
        for field, variable_id in mapping.items():
            if row.get(field) is None:
                continue
            output.append(
                {
                    "decision_time": decision,
                    "entity_id": entity,
                    "variable_id": variable_id,
                    "value": row[field],
                    "source_modality": "benchmark" if role == "benchmark" else "underlying_market",
                    "available_at": available,
                    "quality_state": quality,
                    "missingness_state": _missingness(quality),
                    "record_lineage_id": lineage,
                    "source_id": row.get("source_id"),
                    "attributes": {"role": role, "decision_aligned_to_available": aligned},
                }
            )


def _append_options(
    output: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    context: ExecutionContext,
    policy: LegacyAdapterPolicy,
) -> None:
    contract_map = {str(row.get("contract_key")): row for row in contracts}
    mapping = {
        "bid": "option.bid",
        "ask": "option.ask",
        "last_price": "option.last_price",
        "volume": "option.volume",
        "open_interest": "option.open_interest",
        "implied_volatility": "option.implied_volatility",
        "risk_free_rate": "option.risk_free_rate",
        "dividend_yield": "option.dividend_yield",
    }
    for row in quotes:
        contract_key = str(row.get("contract_key") or "")
        if not contract_key:
            raise ContractError("P4_S4_P2_OPTION_CONTRACT_KEY_MISSING", "option quote is missing contract_key")
        contract = contract_map.get(contract_key, {})
        decision, available, aligned = _decision_and_available(row, context, policy)
        attributes = {
            "contract_key": contract_key,
            "underlying_id": row.get("underlying") or contract.get("underlying"),
            "expiration_date": row.get("expiration_date") or contract.get("expiration_date"),
            "strike": row.get("strike") or contract.get("strike"),
            "option_type": row.get("option_type") or contract.get("option_type"),
            "decision_aligned_to_available": aligned,
        }
        quality = _quality(row.get("quality_flag"))
        lineage = _lineage(row, prefix="p2-option", policy=policy)
        for field, variable_id in mapping.items():
            if row.get(field) is None:
                continue
            output.append(
                {
                    "decision_time": decision,
                    "entity_id": contract_key,
                    "variable_id": variable_id,
                    "value": row[field],
                    "source_modality": "options",
                    "available_at": available,
                    "quality_state": quality,
                    "missingness_state": _missingness(quality),
                    "record_lineage_id": lineage,
                    "source_id": row.get("source_id"),
                    "attributes": attributes,
                }
            )


def _append_generic(
    output: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    context: ExecutionContext,
    policy: LegacyAdapterPolicy,
    modality: str,
) -> None:
    for row in rows:
        variable_id = row.get("variable_id") or row.get("series_id") or row.get("feature_name")
        value = row.get("value", row.get("feature_value"))
        if variable_id is None or value is None:
            continue
        decision, available, aligned = _decision_and_available(row, context, policy)
        entity_value = row.get("entity_id") or row.get("underlying")
        entity = str(entity_value or "__GLOBAL__")
        quality = _quality(row.get("quality_status") or row.get("quality_flag"))
        attributes = dict(row.get("attributes") or {})
        attributes["decision_aligned_to_available"] = aligned
        output.append(
            {
                "decision_time": decision,
                "entity_id": entity,
                "variable_id": str(variable_id),
                "value": value,
                "source_modality": modality,
                "available_at": available,
                "quality_state": quality,
                "missingness_state": _missingness(quality),
                "record_lineage_id": _lineage(row, prefix=f"p2-{modality}", policy=policy),
                "reference_time": row.get("reference_time"),
                "event_time": row.get("event_time"),
                "published_at": row.get("published_at"),
                "unit": row.get("unit"),
                "source_id": row.get("source_id"),
                "attributes": attributes,
            }
        )


def adapt_p2_artifacts(
    artifacts: dict[str, Any],
    context: ExecutionContext,
    *,
    policy: LegacyAdapterPolicy | None = None,
) -> CanonicalObservationPanel:
    active_policy = policy or LegacyAdapterPolicy()
    output: list[dict[str, Any]] = []
    _append_market(output, _records(artifacts.get("clean_underlying_panel")), context, active_policy)
    _append_market(output, _records(artifacts.get("clean_underlying_trade_panel")), context, active_policy)
    _append_market(output, _records(artifacts.get("clean_benchmark_panel")), context, active_policy, role="benchmark")
    _append_options(
        output,
        _records(artifacts.get("clean_option_quotes_panel")),
        _records(artifacts.get("clean_option_contract_panel")),
        context,
        active_policy,
    )
    _append_generic(output, _records(artifacts.get("clean_macro_br_panel")), context, active_policy, "macro")
    _append_generic(output, _records(artifacts.get("clean_macro_us_panel")), context, active_policy, "macro")
    _append_generic(output, _records(artifacts.get("clean_event_reference_panel")), context, active_policy, "event")
    _append_generic(output, _records(artifacts.get("clean_fundamental_panel")), context, active_policy, "fundamental")
    return CanonicalObservationPanel.model_validate(
        {
            "artifact_id": f"canonical-p2:{stable_hash(output)[:16]}",
            "schema_version": "p4.canonical.v1",
            "pipeline_version": context.pipeline_version,
            "run_id": context.run_id,
            "cycle_id": context.cycle_id,
            "as_of_time": context.as_of_time,
            "created_at": context.created_at,
            "lineage_id": lineage_hash(str(row["record_lineage_id"]) for row in output),
            "records": output,
        }
    )
