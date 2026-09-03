"""Strict P2 RC4.1 → P6 market boundary adapter.

The P2 project uses domain-oriented field names while P6 owns typed execution
models.  This module performs the one explicit translation.  It never invents
instrument economics: missing currency, exchange, exercise style or settlement
must be supplied by an explicit governed market profile.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, time
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Mapping

from ..foundation.hashing import canonical_sha256
from ..orchestration.phase_runner import run_phase


class P2P6CompatibilityError(ValueError):
    pass


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P2P6CompatibilityError(f"{label} must be an object")
    return value


def _records(root: Mapping[str, Any], name: str, *, required: bool = True) -> list[dict[str, Any]]:
    value = root.get(name)
    if value is None and isinstance(root.get("outputs"), Mapping):
        value = root["outputs"].get(name)
    if value is None:
        if required:
            raise P2P6CompatibilityError(f"missing P2 artifact: {name}")
        return []
    panel = _mapping(value, name)
    rows = panel.get("records")
    if not isinstance(rows, list):
        raise P2P6CompatibilityError(f"{name}.records must be an array")
    if not all(isinstance(row, dict) for row in rows):
        raise P2P6CompatibilityError(f"{name}.records must contain objects")
    return deepcopy(rows)


def _artifact(root: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    value = root.get(name)
    if value is None and isinstance(root.get("outputs"), Mapping):
        value = root["outputs"].get(name)
    return value if isinstance(value, Mapping) else None


def _dt(value: object, label: str, *, end_of_day: bool = False) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.max if end_of_day else time.min, tzinfo=UTC)
    elif isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise P2P6CompatibilityError(f"{label} is not ISO-8601: {value}") from exc
            result = datetime.combine(parsed, time.max if end_of_day else time.min, tzinfo=UTC)
    else:
        raise P2P6CompatibilityError(f"{label} is required")
    if result.tzinfo is None or result.utcoffset() is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _optional_dt(value: object, label: str, *, end_of_day: bool = False) -> datetime | None:
    return None if value in (None, "") else _dt(value, label, end_of_day=end_of_day)


def _required_text(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    raise P2P6CompatibilityError(f"required field absent: {'/'.join(names)}")


def _profile_value(row: Mapping[str, Any], profile: Mapping[str, Any], row_names: tuple[str, ...], key: str) -> str:
    for name in row_names:
        value = row.get(name)
        if value not in (None, "", "UNKNOWN"):
            return str(value).upper()
    value = profile.get(key)
    if value in (None, ""):
        raise P2P6CompatibilityError(
            f"P2 does not provide {key}; supply it in an explicit governed market profile"
        )
    return str(value).upper()


def _decimal(value: object, label: str, *, required: bool = False) -> str | None:
    if value in (None, ""):
        if required:
            raise P2P6CompatibilityError(f"{label} is required")
        return None
    try:
        return str(Decimal(str(value)))
    except Exception as exc:
        raise P2P6CompatibilityError(f"{label} is not numeric: {value}") from exc


def _quality(row: Mapping[str, Any]) -> str:
    bid = row.get("bid")
    ask = row.get("ask")
    last = row.get("last_price") if row.get("last_price") not in (None, "") else row.get("last")
    flag = str(row.get("quality_flag") or "").upper()
    execution = str(row.get("execution_status") or "").upper()
    if "STALE" in flag:
        return "STALE"
    if bid not in (None, "") and ask not in (None, ""):
        try:
            if Decimal(str(bid)) > Decimal(str(ask)):
                return "CROSSED"
        except Exception:
            pass
        return "TWO_SIDED_EXECUTABLE" if execution != "NON_EXECUTABLE" else "UNAVAILABLE"
    if bid not in (None, ""):
        return "ONE_SIDED_BID"
    if ask not in (None, ""):
        return "ONE_SIDED_ASK"
    if last not in (None, ""):
        return "TRADE_ONLY"
    return "UNAVAILABLE"


def _panel(name: str, records: list[dict[str, Any]], source_ids: list[str]) -> dict[str, Any]:
    return {
        "artifact_id": f"p2-p6-{name}-{canonical_sha256(records)[:20]}",
        "content_sha256": canonical_sha256(records),
        "records": records,
        "metadata": {
            "adapter": "P2_RC4_1_TO_P6_TYPED_MARKET_V1",
            "source_artifact_ids": sorted(set(source_ids)),
            "record_count": len(records),
        },
    }


def adapt_p2_market_inputs(
    p2_outputs: Mapping[str, Any],
    *,
    decision_time: datetime,
    market_profile: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Translate the real P2 handoff into P6 typed market input artifacts."""
    decision = _dt(decision_time, "decision_time")
    profile = _mapping(market_profile, "market_profile")
    contracts_src = _records(p2_outputs, "clean_option_contract_panel")
    quotes_src = _records(p2_outputs, "clean_option_quotes_panel")
    underlyings_src = _records(p2_outputs, "clean_underlying_trade_panel")

    contract_art = _artifact(p2_outputs, "clean_option_contract_panel") or {}
    quote_art = _artifact(p2_outputs, "clean_option_quotes_panel") or {}
    underlying_art = _artifact(p2_outputs, "clean_underlying_trade_panel") or {}
    contract_source_id = str(contract_art.get("artifact_id") or "p2-clean-option-contract-panel")
    quote_source_id = str(quote_art.get("artifact_id") or "p2-clean-option-quotes-panel")
    underlying_source_id = str(underlying_art.get("artifact_id") or "p2-clean-underlying-trade-panel")

    contracts: list[dict[str, Any]] = []
    contract_ids: set[str] = set()
    for index, row in enumerate(contracts_src):
        contract_id = _required_text(row, "contract_key", "option_id")
        if contract_id in contract_ids:
            raise P2P6CompatibilityError(f"duplicate P2 contract identity: {contract_id}")
        contract_ids.add(contract_id)
        option_type = _required_text(row, "option_type").upper()
        if option_type in {"C", "CALL_OPTION"}:
            option_type = "CALL"
        elif option_type in {"P", "PUT_OPTION"}:
            option_type = "PUT"
        if option_type not in {"CALL", "PUT"}:
            raise P2P6CompatibilityError(f"unsupported option_type: {option_type}")
        first_trade = _dt(row.get("first_seen_date") or row.get("date") or row.get("created_at"), f"contract[{index}].first_trade_date")
        last_trade = _optional_dt(row.get("last_seen_date"), f"contract[{index}].last_trade_date", end_of_day=True)
        expiration = _dt(row.get("expiration_date") or row.get("expiration_calendar_date"), f"contract[{index}].expiration", end_of_day=True)
        multiplier = row.get("contract_size") if row.get("contract_size") not in (None, "") else profile.get("default_multiplier")
        if multiplier in (None, ""):
            raise P2P6CompatibilityError("contract multiplier is absent and no default_multiplier was governed")
        contracts.append({
            "contract_id": contract_id,
            "underlying_id": _required_text(row, "underlying", "underlying_id"),
            "option_type": option_type,
            "strike": _decimal(row.get("strike"), f"contract[{index}].strike", required=True),
            "expiration": expiration.isoformat(),
            "exercise_style": _profile_value(row, profile, ("exercise_style",), "exercise_style"),
            "settlement_type": _profile_value(row, profile, ("settlement_type",), "settlement_type"),
            "multiplier": _decimal(multiplier, f"contract[{index}].multiplier", required=True),
            "currency": _profile_value(row, profile, ("currency",), "currency"),
            "listing_exchange": _profile_value(row, profile, ("listing_exchange", "exchange"), "exchange"),
            "first_trade_date": first_trade.isoformat(),
            "last_trade_date": last_trade.isoformat() if last_trade else None,
            "contract_status": str(row.get("contract_status") or "ACTIVE"),
            "source_artifact_id": contract_source_id,
            "source_record_id": str(row.get("option_id") or contract_id),
        })

    quotes: list[dict[str, Any]] = []
    for index, row in enumerate(quotes_src):
        contract_id = _required_text(row, "contract_key", "option_id")
        if contract_id not in contract_ids:
            raise P2P6CompatibilityError(f"quote references unknown contract: {contract_id}")
        available = _dt(row.get("available_at"), f"quote[{index}].available_at")
        if available > decision:
            raise P2P6CompatibilityError(f"future quote detected for {contract_id}")
        quote_time = _dt(row.get("as_of_date") or row.get("observed_at") or row.get("date") or row.get("available_at"), f"quote[{index}].quote_time")
        quotes.append({
            "contract_id": contract_id,
            "quote_time": quote_time.isoformat(),
            "available_at": available.isoformat(),
            "bid": _decimal(row.get("bid"), f"quote[{index}].bid"),
            "ask": _decimal(row.get("ask"), f"quote[{index}].ask"),
            "bid_size": _decimal(row.get("bid_size"), f"quote[{index}].bid_size"),
            "ask_size": _decimal(row.get("ask_size"), f"quote[{index}].ask_size"),
            "last": _decimal(row.get("last_price") if row.get("last_price") not in (None, "") else row.get("last"), f"quote[{index}].last"),
            "last_size": _decimal(row.get("last_size"), f"quote[{index}].last_size"),
            "volume": _decimal(row.get("volume"), f"quote[{index}].volume"),
            "open_interest": _decimal(row.get("open_interest"), f"quote[{index}].open_interest"),
            "implied_volatility": _decimal(row.get("implied_volatility") if row.get("implied_volatility") not in (None, "") else row.get("iv"), f"quote[{index}].implied_volatility"),
            "quote_quality": _quality(row),
            "source_id": str(row.get("source_id") or f"{quote_source_id}:{contract_id}:{index}"),
        })

    underlyings: list[dict[str, Any]] = []
    for index, row in enumerate(underlyings_src):
        available = _dt(row.get("available_at"), f"underlying[{index}].available_at")
        if available > decision:
            raise P2P6CompatibilityError(f"future underlying record detected: {row.get('underlying')}")
        quote_time = _dt(row.get("as_of_date") or row.get("date") or row.get("available_at"), f"underlying[{index}].quote_time")
        underlyings.append({
            "underlying_id": _required_text(row, "underlying", "underlying_id"),
            "quote_time": quote_time.isoformat(),
            "available_at": available.isoformat(),
            "bid": _decimal(row.get("bid"), f"underlying[{index}].bid"),
            "ask": _decimal(row.get("ask"), f"underlying[{index}].ask"),
            "last": _decimal(row.get("reference_price_t") if row.get("reference_price_t") not in (None, "") else row.get("last"), f"underlying[{index}].last"),
            "currency": _profile_value(row, profile, ("currency",), "currency"),
            "exchange": _profile_value(row, profile, ("exchange",), "exchange"),
            "trading_status": "OPEN" if row.get("tradability_flag", True) else "CLOSED",
            "source_artifact_id": underlying_source_id,
            "source_record_id": str(row.get("source_id") or row.get("underlying") or index),
        })

    source_ids = [contract_source_id, quote_source_id, underlying_source_id]
    outputs = {
        "clean_option_contract_panel": _panel("contracts", contracts, source_ids),
        "clean_option_quotes_panel": _panel("quotes", quotes, source_ids),
        "clean_underlying_trade_panel": _panel("underlyings", underlyings, source_ids),
    }
    receipt_payload = {
        "adapter_id": "P2_RC4_1_TO_P6_TYPED_MARKET_V1",
        "decision_time": decision.isoformat(),
        "profile_id": str(profile.get("profile_id") or "UNNAMED_EXPLICIT_PROFILE"),
        "source_artifact_ids": source_ids,
        "contract_count": len(contracts),
        "quote_count": len(quotes),
        "underlying_count": len(underlyings),
        "pit_validated": True,
        "metadata_invented": False,
        "metadata_supplied_by_governed_profile": sorted(
            key for key in ("currency", "exchange", "exercise_style", "settlement_type", "default_multiplier")
            if profile.get(key) not in (None, "")
        ),
        "production_promotion_allowed": False,
    }
    receipt_payload["content_sha256"] = sha256(
        json.dumps(receipt_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return outputs, receipt_payload


def run_from_p5_and_p2(
    *,
    p5_publication: Mapping[str, Any],
    p2_outputs: Mapping[str, Any],
    market_profile: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = _mapping(p5_publication.get("phase6_strategy_scenario_manifest"), "phase6_strategy_scenario_manifest")
    decision = _dt(manifest.get("decision_time"), "P5 decision_time")
    market_inputs, receipt = adapt_p2_market_inputs(
        p2_outputs,
        decision_time=decision,
        market_profile=market_profile,
    )
    inputs = {
        "phase5_output_handoff_manifest": deepcopy(p5_publication["phase5_output_handoff_manifest"]),
        "phase6_strategy_scenario_manifest": deepcopy(manifest),
        **market_inputs,
    }
    result = run_phase(inputs, configuration)
    result["p2_p6_compatibility_receipt"] = receipt
    return result
