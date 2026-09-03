"""Narrow utilities shared by the P7.S2 bounded context."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
from typing import Any

from pydantic import JsonValue

from ..canonical import content_sha256

_MISSING = object()


def deep_copy_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return deepcopy(record)


def get_path(value: object, path: str, default: object = _MISSING) -> object:
    current: object = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            if default is _MISSING:
                raise KeyError(path)
            return default
        current = current[part]
    return current


def first_path(value: object, paths: tuple[str, ...]) -> tuple[str, object] | None:
    for path in paths:
        try:
            resolved = get_path(value, path)
        except KeyError:
            continue
        if resolved is not None:
            return path, resolved
    return None


def finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            return None
        if not decimal_value.is_finite():
            return None
        result = float(decimal_value)
    elif isinstance(value, (int, float, Decimal)):
        result = float(value)
    else:
        return None
    return result if math.isfinite(result) else None


def parse_aware_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("timestamp must be ISO string or datetime")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return result


def decision_id(candidate_id: str, policy_id: str, status: str, reason_codes: list[str]) -> str:
    payload: dict[str, Any] = {
        "candidate_id": candidate_id,
        "policy_id": policy_id,
        "status": status,
        "reason_codes": sorted(reason_codes),
    }
    return f"elig-{content_sha256(payload)}"


def source_artifact_for_path(path: str) -> str:
    prefix = path.split(".", maxsplit=1)[0]
    return {
        "candidate": "strategy_candidate_panel",
        "risk": "strategy_risk_panel",
        "cost_liquidity": "strategy_cost_liquidity_panel",
        "market_snapshot": "strategy_market_snapshot",
        "lineage": "strategy_lineage_panel",
        "greeks": "strategy_greek_panel",
        "ambiguity_evaluations": "strategy_ambiguity_evaluation_panel",
        "payoffs": "strategy_payoff_panel",
        "scenario_evaluations": "strategy_scenario_evaluation_panel",
    }.get(prefix, "validated_strategy_candidate_bundle")
