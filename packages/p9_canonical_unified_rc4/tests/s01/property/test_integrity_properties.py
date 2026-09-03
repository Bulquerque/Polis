from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quant_pipeline.phase_09.contracts.integrity import canonical_json_bytes, payload_sha256


def test_hash_is_invariant_to_mapping_insertion_order() -> None:
    left = {"b": 2, "a": 1, "nested": {"z": 0, "y": 1}}
    right = {"nested": {"y": 1, "z": 0}, "a": 1, "b": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert payload_sha256(left) == payload_sha256(right)


def test_hash_normalizes_equivalent_decimal_representations() -> None:
    left = {"money": Decimal("1.2300"), "when": datetime(2026, 1, 1, tzinfo=UTC)}
    right = {"money": Decimal("1.23"), "when": datetime(2026, 1, 1, tzinfo=UTC)}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert payload_sha256(left) == payload_sha256(right)


def test_hash_changes_when_economic_value_changes() -> None:
    assert payload_sha256({"return": Decimal("0.01")}) != payload_sha256(
        {"return": Decimal("0.02")}
    )
