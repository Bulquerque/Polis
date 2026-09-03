from __future__ import annotations
from collections.abc import Mapping, Sequence

def validate_required_fields(record: Mapping[str, object], required_fields: Sequence[str], context: str = "record") -> None:
    missing = [field for field in required_fields if field not in record]
    if missing:
        raise ValueError(f"Missing required fields in {context}: {missing}")
