from __future__ import annotations


def validate_required_fields(record: dict, required_fields: list[str], context: str = "record") -> None:
    # Fail fast if a dictionary does not contain all required fields.
    missing = [field for field in required_fields if field not in record]
    if missing:
        raise ValueError(f"Missing required fields in {context}: {missing}")
