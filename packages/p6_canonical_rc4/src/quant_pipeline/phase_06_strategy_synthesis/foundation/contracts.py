"""Recursive contract validation and external artifact parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from .errors import Phase6ContractError
from .hashing import canonical_sha256

FORBIDDEN_FIELDS = frozenset({
    "candidate_score",
    "rank_score",
    "top_k_flag",
    "portfolio_weight",
    "trade_decision",
    "future_return",
    "realized_pnl",
    "final_position_size",
    "execution_price_realized",
})

T = TypeVar("T", bound=BaseModel)


def assert_no_forbidden_fields(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        overlap = sorted(FORBIDDEN_FIELDS.intersection(map(str, value)))
        if overlap:
            raise Phase6ContractError(
                "forbidden downstream field detected",
                "P6_OUTPUT_SCHEMA_INVALID",
                "P6.CONTRACT",
                {"path": path, "fields": overlap},
            )
        for key, child in value.items():
            assert_no_forbidden_fields(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            assert_no_forbidden_fields(child, f"{path}[{index}]")


def parse_external_records(
    value: Any,
    model: type[T],
    artifact_name: str,
    module_id: str,
) -> tuple[T, ...]:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if not isinstance(value, Mapping):
        raise Phase6ContractError(
            "artifact must be a mapping",
            "P6_OUTPUT_SCHEMA_INVALID",
            module_id,
            {"artifact": artifact_name},
        )
    records = value.get("records")
    if not isinstance(records, list):
        raise Phase6ContractError(
            "artifact records must be a list",
            "P6_OUTPUT_SCHEMA_INVALID",
            module_id,
            {"artifact": artifact_name},
        )
    expected_hash = value.get("content_sha256")
    if expected_hash is not None and canonical_sha256(records) != expected_hash:
        raise Phase6ContractError(
            "artifact content hash mismatch",
            "P6_MANIFEST_REFERENCE_INVALID",
            module_id,
            {"artifact": artifact_name},
        )
    assert_no_forbidden_fields(records, f"{artifact_name}.records")
    try:
        return tuple(TypeAdapter(list[model]).validate_python(records))
    except ValidationError as exc:
        raise Phase6ContractError(
            "artifact record schema invalid",
            "P6_OUTPUT_SCHEMA_INVALID",
            module_id,
            {"artifact": artifact_name, "errors": exc.errors(include_url=False)[:10]},
        ) from exc


def external_artifact_id(value: Any, artifact_name: str, module_id: str) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if not isinstance(value, Mapping) or not isinstance(value.get("artifact_id"), str):
        raise Phase6ContractError(
            "artifact_id is required",
            "P6_MANIFEST_REFERENCE_INVALID",
            module_id,
            {"artifact": artifact_name},
        )
    return value["artifact_id"]
