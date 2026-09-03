"""Availability and lineage evidence checks for the P5 RC34 boundary."""

from __future__ import annotations

from typing import Any, Mapping

from .p5_utils import normalized, raw_records


def availability_map(artifact: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(artifact, Mapping):
        return {}
    output: dict[str, str] = {}
    for row in raw_records(artifact):
        if isinstance(row, Mapping) and row.get("artifact_type") is not None:
            output[str(row["artifact_type"])] = str(row.get("availability", "UNAVAILABLE"))
    return output


def lineage_map(artifact: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(artifact, Mapping):
        return {}
    content = artifact.get("content")
    if not isinstance(content, Mapping) or not isinstance(content.get("artifacts"), list):
        return {}
    return {
        str(row["artifact_type"]): row
        for row in content["artifacts"]
        if isinstance(row, Mapping) and row.get("artifact_type") is not None
    }


def availability_reason(
    name: str,
    artifact: Mapping[str, Any],
    availability: Mapping[str, str],
) -> str | None:
    direct = artifact.get("reason_code")
    if direct is not None:
        return str(direct)
    if availability.get(name) in {None, "AVAILABLE"}:
        return None
    return f"P5_{availability[name]}"


def metadata_mismatch(
    reference: Any,
    artifact: Mapping[str, Any],
) -> str | None:
    expected = (
        ("producer_module_id", artifact.get("producer_module_id")),
        ("lineage_id", artifact.get("lineage_id")),
        ("available_at", artifact.get("available_at")),
    )
    for field, actual in expected:
        declared = reference.metadata.get(field)
        if declared is not None and actual is not None and normalized(declared) != normalized(actual):
            return field
    return None


def lineage_mismatch(
    name: str,
    reference: Any,
    artifact: Mapping[str, Any],
    lineage: Mapping[str, Mapping[str, Any]],
) -> str | None:
    row = lineage.get(name)
    if row is None:
        return None
    expected = (
        ("artifact_id", reference.artifact_id),
        ("lineage_id", artifact.get("lineage_id")),
        ("producer_module_id", artifact.get("producer_module_id")),
    )
    for field, value in expected:
        if value is not None and str(row.get(field)) != str(value):
            return field
    return None
