"""Canonical declarative target definitions for P5 offline training."""
from __future__ import annotations

from collections.abc import Iterable

from ..domain.training import TargetDefinition
from ..domain.v2_base import CapabilityStatus


_BASE_TARGETS: tuple[dict[str, object], ...] = (
    {"target_id": "RETURN", "target_family": "RETURN", "economic_definition": "future simple return", "transformation": "SIMPLE_RETURN", "units": "decimal_return", "sign_convention": "positive_is_gain", "minimum_history": 24},
    {"target_id": "DIRECTION", "target_family": "DIRECTION", "economic_definition": "indicator of positive future return", "transformation": "BINARY_SIGN", "units": "probability", "sign_convention": "one_is_positive", "minimum_history": 24},
    {"target_id": "REALIZED_VOLATILITY", "target_family": "VOLATILITY", "economic_definition": "future realized volatility", "transformation": "SQRT_REALIZED_VARIANCE", "units": "annualized_volatility", "sign_convention": "nonnegative", "minimum_history": 40},
    {"target_id": "CONDITIONAL_VOLATILITY", "target_family": "VOLATILITY", "economic_definition": "future conditional volatility", "transformation": "CONDITIONAL_SCALE", "units": "annualized_volatility", "sign_convention": "nonnegative", "minimum_history": 40},
    {"target_id": "JUMP", "target_family": "PATH_RISK", "economic_definition": "future jump event", "transformation": "THRESHOLD_EVENT", "units": "probability", "sign_convention": "one_is_jump", "minimum_history": 40},
    {"target_id": "DRAWDOWN", "target_family": "PATH_RISK", "economic_definition": "future maximum drawdown", "transformation": "POSITIVE_LOSS", "units": "positive_loss", "sign_convention": "positive_is_loss", "minimum_history": 40},
    {"target_id": "PATH_MINIMUM", "target_family": "PATH_RISK", "economic_definition": "minimum cumulative path return", "transformation": "PATH_EXTREMUM", "units": "decimal_return", "sign_convention": "negative_is_loss", "minimum_history": 40},
    {"target_id": "PATH_MAXIMUM", "target_family": "PATH_RISK", "economic_definition": "maximum cumulative path return", "transformation": "PATH_EXTREMUM", "units": "decimal_return", "sign_convention": "positive_is_gain", "minimum_history": 40},
    {"target_id": "TAIL_LOSS", "target_family": "TAIL", "economic_definition": "future tail loss", "transformation": "POSITIVE_LOSS", "units": "positive_loss", "sign_convention": "positive_is_loss", "minimum_history": 60},
    {"target_id": "VALUE_AT_RISK", "target_family": "TAIL", "economic_definition": "future value at risk", "transformation": "LOSS_QUANTILE", "units": "positive_loss", "sign_convention": "positive_is_loss", "minimum_history": 60},
    {"target_id": "EXPECTED_SHORTFALL", "target_family": "TAIL", "economic_definition": "future expected shortfall", "transformation": "TAIL_MEAN", "units": "positive_loss", "sign_convention": "positive_is_loss", "minimum_history": 60},
    {"target_id": "IMPLIED_VOLATILITY_CHANGE", "target_family": "OPTIONS_STATE", "economic_definition": "future change in implied volatility", "transformation": "FIRST_DIFFERENCE", "units": "volatility_points", "sign_convention": "positive_is_increase", "minimum_history": 40, "capability_requirements": ("OPTIONS",)},
    {"target_id": "SKEW_CHANGE", "target_family": "OPTIONS_STATE", "economic_definition": "future change in volatility skew", "transformation": "FIRST_DIFFERENCE", "units": "skew_points", "sign_convention": "positive_is_steepening", "minimum_history": 40, "capability_requirements": ("OPTIONS",)},
    {"target_id": "TERM_STRUCTURE_CHANGE", "target_family": "OPTIONS_STATE", "economic_definition": "future change in volatility term structure", "transformation": "FIRST_DIFFERENCE", "units": "term_structure_points", "sign_convention": "positive_is_steepening", "minimum_history": 40, "capability_requirements": ("OPTIONS",)},
    {"target_id": "LIQUIDITY_STRESS", "target_family": "LIQUIDITY", "economic_definition": "future liquidity stress event", "transformation": "THRESHOLD_EVENT", "units": "probability", "sign_convention": "one_is_stress", "minimum_history": 40, "capability_requirements": ("LIQUIDITY",)},
    {"target_id": "REGIME_TRANSITION", "target_family": "REGIME", "economic_definition": "future regime transition", "transformation": "CATEGORICAL_TRANSITION", "units": "probability", "sign_convention": "category_probability", "minimum_history": 60},
    {"target_id": "DEPENDENCE_CHANGE", "target_family": "DEPENDENCE", "economic_definition": "future dependence-state change", "transformation": "MATRIX_DISTANCE", "units": "distance", "sign_convention": "positive_is_change", "minimum_history": 60},
)


def build_target_registry(observed: Iterable[tuple[str, str, str]]) -> tuple[TargetDefinition, ...]:
    observed_rows = tuple(observed)
    observed_ids = {target_id for target_id, _, _ in observed_rows}
    definitions = [_definition(row, row["target_id"] in observed_ids) for row in _BASE_TARGETS]
    canonical_ids = {item.target_id for item in definitions}
    for target_id, horizon, unit in observed_rows:
        if target_id in canonical_ids:
            continue
        family = infer_target_family(target_id, unit)
        definitions.append(TargetDefinition(
            target_id=target_id,
            target_family=family,
            economic_definition=f"observed point-in-time outcome for {target_id}",
            transformation="UPSTREAM_DECLARED",
            units=unit,
            sign_convention=_sign_convention(unit),
            event_time_definition="prediction_timestamp",
            available_time_definition="max(label_end_time, available_at)",
            horizon=horizon,
            trading_calendar_id="P5_DEFAULT_TRADING_CALENDAR",
            minimum_history=24,
            capability_requirements=(),
            availability_status=CapabilityStatus.AVAILABLE,
        ))
    return tuple(definitions)


def infer_target_family(target_id: str, unit: str) -> str:
    name = target_id.upper()
    if "VOL" in name or "VARIANCE" in name:
        return "VOLATILITY"
    if any(token in name for token in ("VAR", "SHORTFALL", "TAIL")) or unit == "positive_loss":
        return "TAIL"
    if any(token in name for token in ("JUMP", "DRAWDOWN", "PATH_", "GAP")):
        return "PATH_RISK"
    if "LIQUID" in name:
        return "LIQUIDITY"
    if "REGIME" in name:
        return "REGIME"
    if "DEPEND" in name or "CORREL" in name or "COVAR" in name:
        return "DEPENDENCE"
    if "DIRECTION" in name or unit == "probability":
        return "DIRECTION"
    return "RETURN"


def _definition(row: dict[str, object], available: bool) -> TargetDefinition:
    return TargetDefinition(
        target_id=str(row["target_id"]),
        target_family=str(row["target_family"]),
        economic_definition=str(row["economic_definition"]),
        transformation=str(row["transformation"]),
        units=str(row["units"]),
        sign_convention=str(row["sign_convention"]),
        event_time_definition="prediction_timestamp to label_end_time on trading calendar",
        available_time_definition="outcome_available_at <= training_cutoff",
        horizon="1D",
        trading_calendar_id="P5_DEFAULT_TRADING_CALENDAR",
        minimum_history=int(row["minimum_history"]),
        capability_requirements=tuple(row.get("capability_requirements", ())),
        availability_status=CapabilityStatus.AVAILABLE if available else CapabilityStatus.UNAVAILABLE,
    )


def _sign_convention(unit: str) -> str:
    if unit == "positive_loss":
        return "positive_is_loss"
    if unit == "probability":
        return "one_is_event"
    return "positive_is_gain"
