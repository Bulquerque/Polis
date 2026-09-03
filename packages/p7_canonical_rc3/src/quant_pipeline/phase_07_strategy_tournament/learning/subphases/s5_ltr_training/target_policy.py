from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ...domain.canonical import digest
from ...domain.errors import fail
from ...domain.models import Direction, TargetPolicy, Transformation


class TargetSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_id: str
    enabled: bool = True
    source_field: str
    unit: str
    direction: Direction
    denominator: str
    transformation: Transformation = Transformation.IDENTITY
    availability_field: str = "outcome_available_at"
    label_end_field: str = "label_end_time"
    policy_version: str
    costs_included: bool


class MetricSemanticRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric_id: str
    unit: str
    direction: Direction
    denominator: str
    costs_included: bool


def _semantics(records: tuple[dict[str, Any], ...]) -> dict[str, MetricSemanticRecord]:
    result: dict[str, MetricSemanticRecord] = {}
    for raw in records:
        semantic = MetricSemanticRecord.model_validate(raw)
        if semantic.metric_id in result:
            fail("P7_LTR_TARGET_POLICY_INVALID", f"duplicate metric semantic {semantic.metric_id}")
        result[semantic.metric_id] = semantic
    return result


def _validate_source(source: TargetSourceRecord, semantic: MetricSemanticRecord) -> None:
    fields = ("unit", "direction", "denominator", "costs_included")
    for field in fields:
        if getattr(source, field) != getattr(semantic, field):
            fail("P7_LTR_TARGET_UNIT_MISMATCH", f"target {source.target_id} {field} mismatch")


def _policy(source: TargetSourceRecord, semantic: MetricSemanticRecord) -> TargetPolicy:
    _validate_source(source, semantic)
    multiplier = -1.0 if source.direction is Direction.LOWER_BETTER else 1.0
    multiplier *= -1.0 if source.transformation is Transformation.NEGATE else 1.0
    return TargetPolicy(
        target_id=source.target_id,
        source_field=source.source_field,
        unit=source.unit,
        raw_direction=source.direction,
        denominator=source.denominator,
        transformation=source.transformation,
        utility_multiplier=multiplier,
        availability_field=source.availability_field,
        label_end_field=source.label_end_field,
        policy_version=source.policy_version,
        costs_included=source.costs_included,
    )


def _record(policy: TargetPolicy) -> dict[str, Any]:
    result = {
        "target_id": policy.target_id,
        "source_field": policy.source_field,
        "unit": policy.unit,
        "raw_direction": policy.raw_direction.value,
        "denominator": policy.denominator,
        "transformation": policy.transformation.value,
        "utility_multiplier": policy.utility_multiplier,
        "availability_field": policy.availability_field,
        "label_end_field": policy.label_end_field,
        "policy_version": policy.policy_version,
        "costs_included": policy.costs_included,
    }
    result["semantic_hash"] = digest(result)
    return result


def compile_target_policies(
    target_records: tuple[dict[str, Any], ...], semantic_records: tuple[dict[str, Any], ...]
) -> list[dict[str, Any]]:
    semantic_map = _semantics(semantic_records)
    policies: list[TargetPolicy] = []
    seen: set[str] = set()
    for raw in target_records:
        source = TargetSourceRecord.model_validate(raw)
        if not source.enabled:
            continue
        if source.target_id in seen:
            fail("P7_LTR_TARGET_POLICY_INVALID", f"duplicate target ID {source.target_id}")
        seen.add(source.target_id)
        semantic = semantic_map.get(source.source_field)
        if semantic is None:
            fail("P7_LTR_TARGET_POLICY_INVALID", f"unknown source metric {source.source_field}")
        policies.append(_policy(source, semantic))
    if not policies:
        fail("P7_LTR_TARGET_POLICY_INVALID", "at least one enabled target policy is required")
    return [_record(policy) for policy in sorted(policies, key=lambda item: item.target_id)]
