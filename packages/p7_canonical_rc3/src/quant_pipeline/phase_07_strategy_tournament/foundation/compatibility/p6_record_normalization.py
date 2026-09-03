"""Record-level normalization from native P6 RC6.1 to the P7 canonical boundary."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import math
from typing import Any

NUMERIC_FIELDS = frozenset({
    "entry_price_reference", "multiplier", "quantity", "strike", "strategy_scale",
    "entry_cash_flow", "maximum_gain", "maximum_loss", "right_tail_slope",
    "terminal_pnl", "spot_grid", "scenario_cost", "scenario_pnl",
    "scenario_probability", "terminal_payoff", "liquidity_stress", "margin_stress",
    "maximum_path_loss", "expected_net_payoff", "expected_shortfall",
    "lower_quantile", "median_net_payoff", "nominal_utility", "probability_of_profit",
    "regret", "return_on_margin", "return_on_max_loss", "upper_quantile",
    "value_at_risk", "worst_ambiguity_utility", "conservative_entry_cost",
    "fee_estimate", "legging_risk_proxy", "maximum_relative_spread", "quoted_cost",
    "slippage_estimate", "stress_entry_cost", "weakest_leg_liquidity", "delta",
    "gamma", "vega", "theta", "rho", "vanna", "volga", "charm",
    "margin_confidence", "margin_estimate", "relative_scale",
})


def normalize_artifact_records(
    name: str,
    records: list[dict[str, Any]],
    *,
    cycle_id: str,
    decision_time: str,
    market_snapshot_id: str,
    published_candidate_ids: frozenset[str],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if name == "strategy_candidate_panel":
        return _candidate_records(records, cycle_id, decision_time, market_snapshot_id, artifacts)
    if name == "strategy_market_snapshot":
        return _snapshot_records(records, decision_time, market_snapshot_id, artifacts)
    if name == "strategy_risk_panel":
        return _risk_records(records, artifacts)
    if name == "strategy_cost_liquidity_panel":
        return _cost_records(records)
    if name == "candidate_equivalence_panel":
        return _equivalence_records(records, published_candidate_ids)
    if name in {"strategy_leg_panel", "strategy_payoff_panel", "strategy_scenario_evaluation_panel",
                "strategy_ambiguity_evaluation_panel", "strategy_greek_panel", "strategy_lineage_panel",
                "strategy_generation_trace_panel"}:
        filtered = [row for row in records if str(row.get("candidate_id")) in published_candidate_ids]
        return [_normalize_numbers(deepcopy(row)) for row in filtered]
    return [_normalize_numbers(deepcopy(row)) for row in records]


def _candidate_records(
    records: list[dict[str, Any]], cycle_id: str, decision_time: str,
    market_snapshot_id: str, artifacts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    optional = {
        "ambiguity": _candidate_ids(artifacts.get("strategy_ambiguity_evaluation_panel")),
        "greeks": _candidate_ids(artifacts.get("strategy_greek_panel")),
        "equivalence": _candidate_ids(artifacts.get("candidate_equivalence_panel")),
    }
    result: list[dict[str, Any]] = []
    for source in records:
        row = _normalize_numbers(deepcopy(source))
        candidate_id = str(row["candidate_id"])
        currencies = sorted({str(leg.get("currency")) for leg in row.get("legs", []) if leg.get("currency")})
        row.update({
            "cycle_id": cycle_id,
            "decision_time": decision_time,
            "horizon": _horizon(row.pop("horizon_days", None)),
            "market_snapshot_id": market_snapshot_id,
            "currency": currencies[0] if len(currencies) == 1 else None,
            "strategy_class": row.get("origin_template_id"),
            "capabilities": {
                "ambiguity": "AVAILABLE" if candidate_id in optional["ambiguity"] else "UNAVAILABLE",
                "greeks": "AVAILABLE" if candidate_id in optional["greeks"] else "UNAVAILABLE",
                "equivalence": "AVAILABLE" if candidate_id in optional["equivalence"] else "UNAVAILABLE",
                "quality_diversity": "UNAVAILABLE",
            },
        })
        result.append(row)
    return result


def _snapshot_records(
    records: list[dict[str, Any]], decision_time: str, market_snapshot_id: str,
    artifacts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(records) != 1:
        raise ValueError("native P6 strategy_market_snapshot must contain exactly one record")
    row = _normalize_numbers(deepcopy(records[0]))
    currencies = _all_candidate_currencies(artifacts.get("strategy_candidate_panel"))
    row.update({
        "market_snapshot_id": market_snapshot_id,
        "market_snapshot_time": decision_time,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "calendar_id": row.get("calendar_id"),
        "clock_basis": "P6_VALIDATED_DECISION_ANCHOR",
    })
    return [row]


def _risk_records(records: list[dict[str, Any]], artifacts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    payoff_map = _index(artifacts.get("strategy_payoff_panel"))
    qualification_map = _index(artifacts.get("strategy_qualification_panel"))
    result: list[dict[str, Any]] = []
    for source in records:
        row = _normalize_numbers(deepcopy(source))
        candidate_id = str(row["candidate_id"])
        qualification = qualification_map.get(candidate_id)
        if qualification is not None:
            q = _normalize_numbers(deepcopy(qualification))
            row.update({key: q.get(key) for key in (
                "maximum_loss_proven", "margin_estimate", "margin_method", "margin_scope",
                "margin_confidence", "margin_status", "data_quality_status",
            )})
        else:
            payoff = _normalize_numbers(deepcopy(payoff_map.get(candidate_id, {})))
            max_loss = row.get("maximum_loss")
            row["maximum_loss_proven"] = (
                max_loss is not None and payoff.get("maximum_loss") == max_loss
                and _as_number(payoff.get("right_tail_slope")) is not None
                and float(payoff["right_tail_slope"]) >= 0
            )
            if row["maximum_loss_proven"]:
                row.update({
                    "margin_estimate": max_loss,
                    "margin_method": "DEFINED_RISK_UPPER_BOUND",
                    "margin_scope": "STANDALONE_CANDIDATE",
                    "margin_confidence": None,
                    "margin_status": "DERIVED_FROM_PUBLISHED_PAYOFF",
                })
        result.append(row)
    return result


def _cost_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in records:
        row = _normalize_numbers(deepcopy(source))
        relative_spread = _as_number(row.get("maximum_relative_spread"))
        liquidity_score = None if relative_spread is None else max(0.0, min(1.0, 1.0 - relative_spread))
        row.update({
            "entry_cost": row.get("conservative_entry_cost"),
            "entry_cost_method": "P6_CONSERVATIVE_ENTRY_COST",
            "liquidity_value": row.get("weakest_leg_liquidity"),
            "liquidity_metric": "WEAKEST_LEG_LIQUIDITY",
            "liquidity_unit": "P6_RAW_LIQUIDITY_MEASURE",
            "liquidity_score": liquidity_score,
            "liquidity_score_method": "ONE_MINUS_MAXIMUM_RELATIVE_SPREAD",
        })
        result.append(row)
    return result


def _equivalence_records(records: list[dict[str, Any]], published: frozenset[str]) -> list[dict[str, Any]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        clusters[str(row.get("equivalence_cluster_id"))].append(row)
    representatives = {
        cluster: next((str(row["candidate_id"]) for row in rows if row.get("representative") is True), None)
        for cluster, rows in clusters.items()
    }
    result: list[dict[str, Any]] = []
    for source in records:
        candidate_id = str(source.get("candidate_id"))
        if candidate_id not in published:
            continue
        row = _normalize_numbers(deepcopy(source))
        row["representative_candidate_id"] = representatives.get(str(row.get("equivalence_cluster_id")))
        result.append(row)
    return result


def _normalize_numbers(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_numbers(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_numbers(item, field_name) for item in value]
    if isinstance(value, str) and field_name in NUMERIC_FIELDS:
        parsed = _as_number(value)
        return parsed if parsed is not None else value
    return value


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, str):
        try:
            numeric = Decimal(value)
        except InvalidOperation:
            return None
        if not numeric.is_finite():
            return None
        result = float(numeric)
        return result if math.isfinite(result) else None
    return None


def _horizon(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("native P6 candidate horizon_days must be a positive integer")
    return f"{value}_calendar_days"


def _candidate_ids(artifact: Mapping[str, Any] | None) -> frozenset[str]:
    if not artifact:
        return frozenset()
    return frozenset(str(row.get("candidate_id")) for row in artifact.get("records", []) if row.get("candidate_id"))


def _index(artifact: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not artifact:
        return {}
    return {str(row["candidate_id"]): dict(row) for row in artifact.get("records", []) if row.get("candidate_id")}


def _all_candidate_currencies(artifact: Mapping[str, Any] | None) -> frozenset[str]:
    if not artifact:
        return frozenset()
    values: set[str] = set()
    for row in artifact.get("records", []):
        values.update(str(leg["currency"]) for leg in row.get("legs", []) if leg.get("currency"))
    return frozenset(values)
