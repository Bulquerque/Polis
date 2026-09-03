"""Small B3 ingress adapter; it consumes already parsed official records."""

from __future__ import annotations

from hashlib import sha256
import json


def _lineage(row: dict) -> str:
    value = row.get("lineage_id") or row.get("source_artifact_id") or row.get("instrument_id") or row.get("symbol")
    return sha256(json.dumps({"source": "B3_PUBLIC_DATA", "value": value}, sort_keys=True).encode()).hexdigest()


def normalize_b3_instrument(row: dict) -> dict:
    native_id = str(row.get("instrument_id") or row.get("native_instrument_id") or "").strip()
    if not native_id:
        raise ValueError("B3 instrument requires official instrument_id")
    option = bool(row.get("underlying_id") or row.get("option_type") or row.get("strike") is not None)
    kind = "OPTION" if option else "EQUITY"
    return {
        **row,
        "canonical_instrument_id": f"BR:B3:{kind}:{native_id}",
        "native_instrument_id": native_id,
        "native_symbol": row.get("symbol") or row.get("option_contract_id"),
        "country": "BR", "venue": "B3", "currency": "BRL",
        "asset_class": "OPTION" if option else "EQUITY",
        "instrument_type": kind,
        "underlying_canonical_id": f"BR:B3:EQUITY:{row['underlying_id']}" if row.get("underlying_id") else None,
        "source_id": "B3_PUBLIC_DATA", "lineage_id": _lineage(row),
    }


def normalize_b3_observation(row: dict) -> dict:
    result = dict(row)
    result.update({"country": "BR", "venue": "B3", "currency": "BRL", "source_id": "B3_PUBLIC_DATA"})
    result.setdefault("lineage_id", _lineage(row))
    return result
