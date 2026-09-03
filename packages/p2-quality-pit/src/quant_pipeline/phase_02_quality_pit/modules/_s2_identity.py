"""Identity and domain primitives for P2.S2.

The public ``contract_key`` remains migration-compatible with the current S4
when an explicit option_id is available.  ``canonical_contract_key`` carries
an improved versioned option identity for later S4 migration without breaking
the current pipeline surface.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ._module_executor import ContractValidationError
from ._option_identity import (
    canonical_economic_contract_key,
    normalize_expiration_date,
    normalize_option_type_code,
    normalize_strike_token,
)

IDENTITY_POLICY_VERSION = "p2.identity.v1"
DOMAIN_POLICY_VERSION = "p2.domain.v1"

_DOMAINS = {
    "MACRO",
    "BENCHMARK",
    "CALENDAR",
    "CORPORATE_ACTION",
    "UNDERLYING",
    "OPTION_CONTRACT",
    "OPTION_QUOTE",
    "DOCUMENT",
    "EVENT",
    "CONTEXT",
    "UNKNOWN",
}


def _digest(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def normalize_symbol(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return " ".join(str(value).strip().upper().split())


def mapped_symbol(symbol: str | None, source_id: str | None, config: dict) -> str | None:
    if symbol is None:
        return None
    mappings = config.get("symbol_mappings") or {}
    if not isinstance(mappings, dict):
        return symbol

    # Source-scoped mapping takes precedence over global mapping.
    if source_id and isinstance(mappings.get(source_id), dict):
        source_map = mappings[source_id]
        return normalize_symbol(source_map.get(symbol) or source_map.get(symbol.upper()) or symbol)
    return normalize_symbol(mappings.get(symbol) or mappings.get(symbol.upper()) or symbol)


def normalize_option_type(value: Any) -> str:
    return normalize_option_type_code(value, strict=True)


def normalize_strike(value: Any) -> str:
    return normalize_strike_token(value)


def normalize_expiration(value: Any) -> str:
    return normalize_expiration_date(value)

def classify_domain(row: dict) -> str:
    explicit = str(row.get("record_domain") or "").strip().upper()
    if explicit in _DOMAINS:
        return explicit

    document_type = str(row.get("document_type") or row.get("record_type") or "").strip().lower()
    if document_type in {"document", "news", "filing", "report"}:
        return "DOCUMENT"
    if document_type in {"event"}:
        return "EVENT"

    if row.get("action_type") not in (None, "") or (
        row.get("effective_date") not in (None, "") and row.get("adjustment_factor") not in (None, "")
    ):
        return "CORPORATE_ACTION"

    option_signature = all(row.get(field) not in (None, "") for field in ("expiration_date", "strike", "option_type"))
    if option_signature:
        quote_fields = ("bid", "ask", "last", "last_price", "volume", "open_interest")
        return "OPTION_QUOTE" if any(row.get(field) not in (None, "") for field in quote_fields) else "OPTION_CONTRACT"

    if row.get("benchmark_id") not in (None, ""):
        return "BENCHMARK"
    if row.get("series_id") not in (None, ""):
        return "MACRO"
    if row.get("is_trading_day") not in (None, "") or row.get("holiday_code") not in (None, ""):
        return "CALENDAR"

    symbol_present = any(row.get(field) not in (None, "") for field in ("underlying", "ticker", "symbol"))
    market_value_present = any(row.get(field) not in (None, "") for field in ("open", "high", "low", "close", "price"))
    if symbol_present and market_value_present:
        return "UNDERLYING"

    if document_type in {"context", "source", "metadata"}:
        return "CONTEXT"
    return "UNKNOWN"


def provider_instrument_id(row: dict) -> str | None:
    for field in ("provider_instrument_id", "option_id", "symbol", "ticker", "underlying", "isin", "figi"):
        value = row.get(field)
        if value not in (None, ""):
            return str(value).strip()
    return None


def canonical_instrument_id(row: dict, domain: str, config: dict) -> tuple[str | None, str | None]:
    source_id = str(row.get("source_id")) if row.get("source_id") not in (None, "") else None
    explicit = row.get("canonical_instrument_id")
    if explicit not in (None, ""):
        return str(explicit), normalize_symbol(row.get("underlying") or row.get("ticker") or row.get("symbol"))

    for field, prefix in (("figi", "FIGI"), ("isin", "ISIN")):
        if row.get(field) not in (None, ""):
            return f"{prefix}:{str(row[field]).strip().upper()}", normalize_symbol(
                row.get("underlying") or row.get("ticker") or row.get("symbol")
            )

    raw_symbol = normalize_symbol(row.get("underlying") or row.get("ticker") or row.get("symbol"))
    symbol = mapped_symbol(raw_symbol, source_id, config)
    if symbol is None:
        if domain in {"OPTION_CONTRACT", "OPTION_QUOTE", "UNDERLYING"}:
            return None, None
        return None, None

    identity_payload = {
        "market": normalize_symbol(row.get("market")),
        "exchange": normalize_symbol(row.get("exchange")),
        "asset_class": normalize_symbol(row.get("asset_class")) or ("EQUITY" if domain == "UNDERLYING" else None),
        "symbol": symbol,
        "currency": normalize_symbol(row.get("currency")),
    }
    # If metadata is sparse, scope the identity to the source instead of falsely
    # merging symbols from unrelated providers.
    if not identity_payload["market"] and not identity_payload["exchange"] and source_id:
        identity_payload["source_scope"] = source_id
    return _digest("inst1", identity_payload), symbol


def canonical_option_contract_key(row: dict, canonical_underlying_id: str) -> str:
    return canonical_economic_contract_key(row, canonical_underlying_id)

def legacy_option_contract_key(row: dict) -> str | None:
    """Match the current S4 public key when explicit option_id is available."""
    option_id = row.get("option_id")
    expiration = row.get("expiration_date")
    if option_id in (None, "") or expiration in (None, ""):
        return None
    # Mirrors _p2_semantic_helpers.stable_key(..., ("option_id", "expiration_date")).
    return json.dumps((option_id, normalize_expiration(expiration)), sort_keys=True, default=str)


def _observation_payload(row: dict) -> dict:
    ignored = {
        "observation_key",
        "contract_key",
        "canonical_contract_key",
        "canonical_instrument_id",
        "identity_key_type",
        "identity_policy_version",
        "domain_policy_version",
    }
    return {key: value for key, value in row.items() if key not in ignored and key != "_provenance"}


def observation_key(row: dict) -> tuple[str, str]:
    provenance = row.get("_provenance") if isinstance(row.get("_provenance"), dict) else {}
    raw_row_number = provenance.get("raw_row_number")
    artifact_identity = (
        provenance.get("physical_file_hash")
        or row.get("physical_file_hash")
        or provenance.get("raw_artifact_id")
        or row.get("raw_artifact_id")
    )
    if raw_row_number not in (None, "") and artifact_identity not in (None, ""):
        return _digest(
            "obs1",
            {
                "source_id": row.get("source_id"),
                "artifact": artifact_identity,
                "raw_row_number": raw_row_number,
                "revision_id": row.get("revision_id"),
            },
        ), "PHYSICAL_PROVENANCE"

    return _digest(
        "obs1",
        {
            "source_id": row.get("source_id"),
            "available_at": row.get("available_at"),
            "reference_date": row.get("reference_date"),
            "row": _observation_payload(row),
        },
    ), "LEGACY_DERIVED"


def synthetic_forbidden(row: dict) -> bool:
    if bool(row.get("synthetic")):
        return True
    if str(row.get("instrument_type") or "").strip().upper() == "SYNTHETIC":
        return True
    for field in ("underlying", "ticker", "symbol"):
        value = row.get(field)
        if value not in (None, "") and str(value).strip().lower().startswith("synthetic"):
            return True
    return False


def harmonize_record(row: dict, config: dict) -> dict:
    if synthetic_forbidden(row):
        raise ContractValidationError("no_synthetic_instrument violation")

    domain = classify_domain(row)
    canonical_id, normalized_symbol = canonical_instrument_id(row, domain, config)
    provider_id = provider_instrument_id(row)

    output = dict(row)
    output["record_domain"] = domain
    output["domain_policy_version"] = DOMAIN_POLICY_VERSION
    output["identity_policy_version"] = IDENTITY_POLICY_VERSION
    if provider_id:
        output["provider_instrument_id"] = provider_id
    if canonical_id:
        output["canonical_instrument_id"] = canonical_id
    if normalized_symbol and domain in {"UNDERLYING", "OPTION_CONTRACT", "OPTION_QUOTE"}:
        output["underlying"] = normalized_symbol

    if domain in {"OPTION_CONTRACT", "OPTION_QUOTE"}:
        if not canonical_id:
            raise ContractValidationError("P2_S2_M02_OPTION_UNDERLYING_MISSING")
        canonical_contract = canonical_option_contract_key(row, canonical_id)
        public_contract = legacy_option_contract_key(row) or canonical_contract
        output["canonical_contract_key"] = canonical_contract
        output["contract_key"] = public_contract
        output["contract_key_mode"] = "LEGACY_OPTION_ID_EXPIRATION" if public_contract != canonical_contract else "CANONICAL_OPTION"
        output["identity_key_type"] = "OPTION_CONTRACT"
        output["option_type"] = normalize_option_type(row.get("option_type"))
        output["expiration_date"] = normalize_expiration(row.get("expiration_date"))
        output["strike_normalized"] = normalize_strike(row.get("strike"))
    elif canonical_id:
        output["contract_key"] = canonical_id
        output["identity_key_type"] = "INSTRUMENT"
    else:
        output["contract_key"] = _digest(
            "rec1",
            {
                "source_id": row.get("source_id"),
                "domain": domain,
                "reference_date": row.get("reference_date"),
            },
        )
        output["identity_key_type"] = "RECORD"

    obs_key, obs_mode = observation_key(output)
    output["observation_key"] = obs_key
    output["observation_key_mode"] = obs_mode
    return output
