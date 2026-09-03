"""Closed contracts for promoted prior-cycle feedback consumed by P5.

Feedback is deliberately narrow: it may alter research eligibility, bounded
configuration, budgets, approved thresholds, or deprecation state. It may not
carry forecasts, labels, scores, or arbitrary executable configuration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..boundary.models import canonical_sha256
from .core import FrozenModel


class FeedbackEffectType(StrEnum):
    CHALLENGER_ELIGIBILITY = "CHALLENGER_ELIGIBILITY"
    HYPERPARAMETER_BOUNDS = "HYPERPARAMETER_BOUNDS"
    RESEARCH_BUDGET = "RESEARCH_BUDGET"
    APPROVED_THRESHOLDS = "APPROVED_THRESHOLDS"
    MODEL_DEPRECATION = "MODEL_DEPRECATION"


_PAYLOAD_FIELDS: dict[FeedbackEffectType, frozenset[str]] = {
    FeedbackEffectType.CHALLENGER_ELIGIBILITY: frozenset({"eligible"}),
    FeedbackEffectType.HYPERPARAMETER_BOUNDS: frozenset({"parameter", "minimum", "maximum"}),
    FeedbackEffectType.RESEARCH_BUDGET: frozenset(
        {"budget_name", "maximum_attempts", "maximum_compute_seconds"}
    ),
    FeedbackEffectType.APPROVED_THRESHOLDS: frozenset({"threshold_name", "value"}),
    FeedbackEffectType.MODEL_DEPRECATION: frozenset({"model_artifact_id", "deprecated"}),
}


class PriorCycleFeedbackRecord(FrozenModel):
    feedback_id: str = Field(min_length=1)
    effect_type: FeedbackEffectType
    effect_payload: dict[str, bool | int | float | str]
    resolver_id: str | None = None
    target_id: str | None = None
    horizon: str | None = None
    reason_code: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_effect_payload(self) -> "PriorCycleFeedbackRecord":
        expected = _PAYLOAD_FIELDS[self.effect_type]
        observed = frozenset(self.effect_payload)
        if observed != expected:
            raise ValueError(
                f"{self.effect_type} requires payload fields {sorted(expected)}; "
                f"observed {sorted(observed)}"
            )
        if self.effect_type in {
            FeedbackEffectType.CHALLENGER_ELIGIBILITY,
            FeedbackEffectType.HYPERPARAMETER_BOUNDS,
        } and not self.resolver_id:
            raise ValueError(f"{self.effect_type} requires resolver_id")
        if self.effect_type is FeedbackEffectType.HYPERPARAMETER_BOUNDS:
            lower = float(self.effect_payload["minimum"])
            upper = float(self.effect_payload["maximum"])
            if lower > upper:
                raise ValueError("hyperparameter minimum cannot exceed maximum")
        if self.effect_type is FeedbackEffectType.RESEARCH_BUDGET:
            attempts = int(self.effect_payload["maximum_attempts"])
            seconds = float(self.effect_payload["maximum_compute_seconds"])
            if attempts < 0 or seconds < 0:
                raise ValueError("research budgets must be non-negative")
        if self.effect_type is FeedbackEffectType.APPROVED_THRESHOLDS:
            value = float(self.effect_payload["value"])
            if not 0.0 <= value <= 1.0:
                raise ValueError("approved threshold must be between zero and one")
        return self


class PriorCycleFeedbackReport(FrozenModel):
    schema_version: Literal["P9-P5-FEEDBACK-V1"] = "P9-P5-FEEDBACK-V1"
    feedback_route: Literal["NEXT_CYCLE_ONLY"] = "NEXT_CYCLE_ONLY"
    source_phase: Literal["P9"] = "P9"
    source_run_id: str = Field(min_length=1)
    source_cycle_id: str = Field(min_length=1)
    promotion_status: Literal["PROMOTED"] = "PROMOTED"
    promotion_decision_id: str = Field(min_length=1)
    created_at: datetime
    available_at: datetime
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    records: tuple[PriorCycleFeedbackRecord, ...]

    @field_validator("created_at", "available_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("feedback timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_report(self) -> "PriorCycleFeedbackReport":
        if self.available_at < self.created_at:
            raise ValueError("feedback available_at cannot precede created_at")
        identifiers = [record.feedback_id for record in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("feedback IDs must be unique within a report")
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        if canonical_sha256(payload) != self.content_sha256:
            raise ValueError("feedback content_sha256 does not match canonical report content")
        return self

    def projected_records(self) -> tuple[dict[str, Any], ...]:
        """Return only the explicitly permitted projection consumed downstream."""
        common = {
            "source_phase": self.source_phase,
            "source_run_id": self.source_run_id,
            "source_cycle_id": self.source_cycle_id,
            "promotion_status": self.promotion_status,
            "promotion_decision_id": self.promotion_decision_id,
            "created_at": self.created_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "source_content_sha256": self.content_sha256,
        }
        return tuple({**record.model_dump(mode="json"), **common} for record in self.records)
