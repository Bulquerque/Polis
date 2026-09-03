from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quant_pipeline.phase_09.contracts.integrity import canonical_json_bytes, payload_sha256


def test_canonical_hash_is_key_order_invariant() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert payload_sha256(left) == payload_sha256(right)


def test_canonical_hash_normalizes_decimal_and_datetime() -> None:
    value = {
        "time": datetime(2026, 1, 1, tzinfo=UTC),
        "amount": Decimal("10.5000"),
    }
    payload = canonical_json_bytes(value)
    assert b'"10.5"' in payload
    assert b"2026-01-01T00:00:00.000000Z" in payload
