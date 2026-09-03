from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..errors import P7ContractError


def artifact_records(artifact: Mapping[str, Any], expected_name: str) -> list[dict[str, Any]]:
    actual_name = artifact.get("artifact_name")
    if actual_name != expected_name:
        raise P7ContractError(
            "P7_HANDOFF_ARTIFACT_NAME_MISMATCH",
            f"expected {expected_name}, got {actual_name}",
        )
    records = artifact.get("records")
    if not isinstance(records, list):
        raise P7ContractError(
            "P7_HANDOFF_RECORDS_INVALID",
            f"{expected_name}.records must be a list",
        )
    return [dict(record) for record in records]


def parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise P7ContractError("P7_HANDOFF_TIMESTAMP_INVALID", f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P7ContractError("P7_HANDOFF_TIMESTAMP_INVALID", f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise P7ContractError("P7_HANDOFF_TIMESTAMP_INVALID", f"{field} must be timezone-aware")
    return parsed


def candidate_index(records: list[dict[str, Any]], artifact_name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise P7ContractError(
                "P7_HANDOFF_CANDIDATE_ID_INVALID",
                f"{artifact_name} contains a record without candidate_id",
            )
        if candidate_id in result:
            raise P7ContractError(
                "P7_HANDOFF_CANDIDATE_DUPLICATE",
                f"{artifact_name} contains duplicate candidate {candidate_id}",
            )
        result[candidate_id] = record
    return result
