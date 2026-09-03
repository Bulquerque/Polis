from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from .errors import S2ContractError


class ExecutionProfile(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    QUALIFICATION = "QUALIFICATION"


class ValidationStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class TemporalEvidenceClass(StrEnum):
    RECORD_LEVEL = "RECORD_LEVEL_TEMPORAL"
    ARTIFACT_LEVEL = "ARTIFACT_LEVEL_TEMPORAL"
    RESOLVED_BY_REFERENCE = "RESOLVED_BY_REFERENCE"
    MISSING = "MISSING_TEMPORAL_EVIDENCE"


class TemporalDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED_FUTURE = "REJECTED_FUTURE"
    QUARANTINED_MISSING_TEMPORAL = "QUARANTINED_MISSING_TEMPORAL"


@dataclass(frozen=True, slots=True)
class S2Settings:
    pipeline_version: str = "V14.1-RC4.1"
    execution_profile: ExecutionProfile = ExecutionProfile.DEVELOPMENT
    strict_artifact_hashes: bool = True
    block_on_future_record: bool = True
    qualification_blocks_missing_available_at: bool = True
    development_quarantines_missing_available_at: bool = True
    require_seed_manifest_in_qualification: bool = True
    require_concrete_model_inventory_in_qualification: bool = True

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "S2Settings":
        value = value or {}
        raw_profile = str(value.get("execution_profile", "DEVELOPMENT")).upper()
        try:
            profile = ExecutionProfile(raw_profile)
        except ValueError as exc:
            raise S2ContractError(
                "P3_S2_EXECUTION_PROFILE_INVALID",
                f"Unsupported execution_profile: {raw_profile}",
            ) from exc
        return cls(
            pipeline_version=str(value.get("pipeline_version", "V14.1-RC4.1")),
            execution_profile=profile,
            strict_artifact_hashes=bool(value.get("strict_artifact_hashes", True)),
            block_on_future_record=bool(value.get("block_on_future_record", True)),
            qualification_blocks_missing_available_at=bool(
                value.get("qualification_blocks_missing_available_at", True)
            ),
            development_quarantines_missing_available_at=bool(
                value.get("development_quarantines_missing_available_at", True)
            ),
            require_seed_manifest_in_qualification=bool(
                value.get("require_seed_manifest_in_qualification", True)
            ),
            require_concrete_model_inventory_in_qualification=bool(
                value.get("require_concrete_model_inventory_in_qualification", True)
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationWindow:
    as_of: datetime
    evaluation_start: datetime | None
    evaluation_end: datetime | None
    warmup_start: datetime | None
    warmup_end: datetime | None
    timezone: str
    boundary_rule: str


@dataclass(frozen=True, slots=True)
class ResolvedResource:
    resource_id: str
    path: str
    value: Any
