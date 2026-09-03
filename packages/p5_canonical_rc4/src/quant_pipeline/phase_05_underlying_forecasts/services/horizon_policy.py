"""Versioned binding between P5 forecast horizons and P4 horizon groups."""
from __future__ import annotations

from ..errors import ContractError

_POLICY_VERSION = "P4-V14.9-P5-RC34.1-CONTRACT-CLOSURE-RC4-HORIZON-V2"
_PRIMARY = {"1D": "SHORT", "5D": "MEDIUM", "21D": "LONG"}
_ALLOWED = {
    "1D": ("SHORT", "CROSS_HORIZON"),
    "5D": ("MEDIUM", "CROSS_HORIZON"),
    "21D": ("LONG", "CROSS_HORIZON"),
}


def policy_version() -> str:
    return _POLICY_VERSION


def primary_horizon_group(horizon: str) -> str:
    normalized = horizon.upper()
    try:
        return _PRIMARY[normalized]
    except KeyError as exc:
        raise ContractError(f"no P4 horizon-group binding for P5 horizon {horizon}") from exc


def allowed_horizon_groups(horizon: str) -> tuple[str, ...]:
    normalized = horizon.upper()
    try:
        return _ALLOWED[normalized]
    except KeyError as exc:
        raise ContractError(f"no P4 horizon-group policy for P5 horizon {horizon}") from exc


def passport_target_scope(primary_horizon: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    mapping = {
        "SHORT": (("excess_return_1d",), ("1D",)),
        "MEDIUM": (("excess_return_5d",), ("5D",)),
        "LONG": (("excess_return_21d",), ("21D",)),
        "CROSS_HORIZON": (
            ("excess_return_1d", "excess_return_5d", "excess_return_21d"),
            ("1D", "5D", "21D"),
        ),
    }
    try:
        return mapping[primary_horizon.upper()]
    except KeyError as exc:
        raise ContractError(f"unsupported P4 hypothesis primary_horizon: {primary_horizon}") from exc
