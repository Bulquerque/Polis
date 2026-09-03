from __future__ import annotations
from pathlib import Path
from typing import Iterable, Mapping, Any
import unicodedata

class ZeroTrustValidationError(ValueError):
    pass

FORBIDDEN_ECONOMIC_FIELDS = {
    'future_return','target','signal_direction','candidate_score','rank_score',
    'portfolio_weight','realized_pnl','trade_decision','execution_price','position_size'
}

def normalize_field_name(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).casefold()

def require_keys(data: Mapping[str, Any], keys: Iterable[str], context: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ZeroTrustValidationError(f'{context}: missing required keys {missing}')

def scan_forbidden_fields(fields: Iterable[str]) -> set[str]:
    forbidden = {normalize_field_name(field) for field in FORBIDDEN_ECONOMIC_FIELDS}
    return {field for field in fields if normalize_field_name(field) in forbidden}

def validate_no_forbidden_fields(fields: Iterable[str], context: str) -> None:
    found = scan_forbidden_fields(fields)
    if found:
        raise ZeroTrustValidationError(f'{context}: forbidden economic fields {sorted(found)}')

def ensure_file_exists(path: str | Path, context: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise ZeroTrustValidationError(f'{context}: missing file {p}')
    return p
