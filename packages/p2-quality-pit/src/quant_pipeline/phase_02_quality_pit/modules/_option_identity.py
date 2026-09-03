"""Shared option identity primitives for P2.

This module is the single authority for canonical option economic identity used
by S2 and S4.  The public ``contract_key`` remains a compatibility surface;
``canonical_contract_key`` is an opaque, deterministic economic identity.
Provider-only fallback identities are explicit and are never treated as full
economic identity.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from ._module_executor import ContractValidationError

OPTION_IDENTITY_POLICY_VERSION = "p2.option_identity.v2"


def _digest(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def normalize_symbol(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return " ".join(str(value).strip().upper().split())


def normalize_option_type_code(value: Any, *, strict: bool = True) -> str:
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if token in {"C", "CALL", "CALL_OPTION"}:
        return "C"
    if token in {"P", "PUT", "PUT_OPTION"}:
        return "P"
    if strict:
        raise ContractValidationError(f"P2_OPTION_IDENTITY_INVALID_OPTION_TYPE: {value!r}")
    return "UNKNOWN"


def normalize_option_type_label(value: Any) -> str:
    code = normalize_option_type_code(value, strict=False)
    return {"C": "CALL", "P": "PUT"}.get(code, "UNKNOWN")


def normalize_strike_token(value: Any) -> str:
    if value in (None, ""):
        raise ContractValidationError("P2_OPTION_IDENTITY_INVALID_STRIKE: strike missing")
    try:
        strike = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ContractValidationError(f"P2_OPTION_IDENTITY_INVALID_STRIKE: {value!r}") from exc
    if not strike.is_finite() or strike <= 0:
        raise ContractValidationError(f"P2_OPTION_IDENTITY_INVALID_STRIKE: {value!r}")
    normalized = format(strike.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def normalize_expiration_date(value: Any) -> str:
    if value in (None, ""):
        raise ContractValidationError("P2_OPTION_IDENTITY_INVALID_EXPIRATION: expiration missing")
    text = str(value).strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    raise ContractValidationError(f"P2_OPTION_IDENTITY_INVALID_EXPIRATION: {value!r}")


def canonical_economic_contract_key(row: dict[str, Any], canonical_underlying_id: str) -> str:
    """Build the canonical economic identity used across S2 and S4."""
    if not canonical_underlying_id:
        raise ContractValidationError("P2_OPTION_IDENTITY_UNDERLYING_MISSING")
    payload = {
        "underlying": canonical_underlying_id,
        "expiration_date": normalize_expiration_date(
            row.get("expiration_date") or row.get("expiration") or row.get("expiry")
        ),
        "option_type": normalize_option_type_code(
            row.get("option_type") or row.get("call_put") or row.get("right"), strict=True
        ),
        "strike": normalize_strike_token(row.get("strike")),
        "exchange": normalize_symbol(row.get("exchange")),
        "market": normalize_symbol(row.get("market")),
        "adjustment_code": str(row.get("adjustment_code") or row.get("deliverable_id") or "").strip() or None,
    }
    return _digest("ock1", payload)


def provider_fallback_contract_key(row: dict[str, Any]) -> tuple[str, list[str]]:
    """Build an explicit provider-scoped fallback without fabricating economics."""
    option_id = str(row.get("option_id") or "").strip()
    if not option_id:
        raise ContractValidationError("option identity requires economic fields or option_id")
    expiration = normalize_expiration_date(
        row.get("expiration_date") or row.get("expiration") or row.get("expiry")
    )
    strike = normalize_strike_token(row.get("strike"))
    source_id = str(row.get("source_id") or "").strip() or None
    reasons: list[str] = []
    if not row.get("canonical_instrument_id") and not row.get("underlying"):
        reasons.append("UNDERLYING_UNKNOWN")
    if normalize_option_type_code(
        row.get("option_type") or row.get("call_put") or row.get("right"), strict=False
    ) == "UNKNOWN":
        reasons.append("OPTION_TYPE_UNKNOWN")
    return _digest(
        "ockp1",
        {
            "source_id": source_id,
            "option_id": option_id,
            "expiration_date": expiration,
            "strike": strike,
        },
    ), reasons


def resolve_canonical_contract_key(row: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Resolve a canonical key using upstream S2 identity first.

    Returns ``(key, identity_mode, quality_reasons)``.  A precomputed upstream
    key is authoritative.  Otherwise economic identity is preferred; provider
    fallback is explicit for legacy rows with incomplete economics.
    """
    upstream = row.get("canonical_contract_key")
    if upstream not in (None, ""):
        return str(upstream), "UPSTREAM_CANONICAL", []

    canonical_underlying = str(row.get("canonical_instrument_id") or "").strip()
    option_type = normalize_option_type_code(
        row.get("option_type") or row.get("call_put") or row.get("right"), strict=False
    )
    if canonical_underlying and option_type in {"C", "P"}:
        return canonical_economic_contract_key(row, canonical_underlying), "ECONOMIC", []

    # Legacy direct-S4 callers may not have passed through S2. Build a stable,
    # provider-independent underlying namespace from explicit economics rather
    # than falling back to provider option IDs. Normal P2 execution always uses
    # the richer S2 canonical_instrument_id path above.
    underlying_symbol = normalize_symbol(row.get("underlying"))
    if underlying_symbol and option_type in {"C", "P"}:
        legacy_underlying = _digest(
            "instlegacy1",
            {
                "symbol": underlying_symbol,
                "market": normalize_symbol(row.get("market")),
                "exchange": normalize_symbol(row.get("exchange")),
            },
        )
        return canonical_economic_contract_key(row, legacy_underlying), "ECONOMIC", []

    return _provider_tuple(row)


def _provider_tuple(row: dict[str, Any]) -> tuple[str, str, list[str]]:
    key, reasons = provider_fallback_contract_key(row)
    return key, "PROVIDER_FALLBACK", reasons
