from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ExecutionProfile(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    QUALIFICATION = "QUALIFICATION"


class ValidationStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class QualityDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNING = "ACCEPTED_WITH_WARNING"
    REJECTED_INVALID = "REJECTED_INVALID"
    REJECTED_UNTRACEABLE = "REJECTED_UNTRACEABLE"


@dataclass(frozen=True, slots=True)
class S1Settings:
    pipeline_version: str = "V14.1-RC4.1"
    execution_profile: ExecutionProfile = ExecutionProfile.DEVELOPMENT
    strict_manifest_hashes: bool = True
    require_precise_manifest_refs_in_qualification: bool = True
    block_if_no_accepted_records: bool = True
    block_on_duplicate_quality_source: bool = True

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "S1Settings":
        value = value or {}
        raw_profile = str(value.get("execution_profile", "DEVELOPMENT")).upper()
        try:
            profile = ExecutionProfile(raw_profile)
        except ValueError as exc:
            raise ValueError(f"Unsupported execution_profile: {raw_profile}") from exc
        return cls(
            pipeline_version=str(value.get("pipeline_version", "V14.1-RC4.1")),
            execution_profile=profile,
            strict_manifest_hashes=bool(value.get("strict_manifest_hashes", True)),
            require_precise_manifest_refs_in_qualification=bool(
                value.get("require_precise_manifest_refs_in_qualification", True)
            ),
            block_if_no_accepted_records=bool(
                value.get("block_if_no_accepted_records", True)
            ),
            block_on_duplicate_quality_source=bool(
                value.get("block_on_duplicate_quality_source", True)
            ),
        )
