from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from .runtime.datetime_utils import parse_aware_datetime


class ExecutionProfile(StrEnum):
    TEST = "TEST"
    REPLAY = "REPLAY"
    LIVE = "LIVE"


class CompatibilityMode(StrEnum):
    RC4_1 = "RC4_1"
    STRICT = "STRICT"


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    profile: ExecutionProfile
    run_id: str
    cycle_id: str
    as_of_time: datetime
    decision_time: datetime
    created_at: datetime
    pipeline_version: str
    contract_generation: str = "V14.9-RC1"
    architecture_revision: str = "P4-INTEGRATED-S1-S9-V1"
    compatibility_mode: CompatibilityMode = CompatibilityMode.RC4_1
    allow_degraded_handoffs: bool = False
    prior_cycle_ids: tuple[str, ...] = ()
    variable_evolution_source_cycle_id: str | None = None
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("run_id", "cycle_id", "pipeline_version", "contract_generation"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be blank")
        object.__setattr__(self, "as_of_time", parse_aware_datetime(self.as_of_time, "as_of_time"))
        object.__setattr__(self, "decision_time", parse_aware_datetime(self.decision_time, "decision_time"))
        object.__setattr__(self, "created_at", parse_aware_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))
        if self.decision_time > self.as_of_time:
            raise ValueError("decision_time cannot be after as_of_time")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionContext":
        profile = ExecutionProfile(str(value.get("profile", "TEST")).upper())
        compatibility = CompatibilityMode(str(value.get("compatibility_mode", "RC4_1")).upper())
        return cls(
            profile=profile,
            run_id=str(value["run_id"]),
            cycle_id=str(value["cycle_id"]),
            as_of_time=parse_aware_datetime(value["as_of_time"], "as_of_time"),
            decision_time=parse_aware_datetime(value.get("decision_time", value["as_of_time"]), "decision_time"),
            created_at=parse_aware_datetime(value["created_at"], "created_at"),
            pipeline_version=str(value["pipeline_version"]),
            contract_generation=str(value.get("contract_generation", "V14.9-RC1")),
            architecture_revision=str(value.get("architecture_revision", "P4-INTEGRATED-S1-S9-V1")),
            compatibility_mode=compatibility,
            allow_degraded_handoffs=bool(value.get("allow_degraded_handoffs", False)),
            prior_cycle_ids=tuple(str(x) for x in value.get("prior_cycle_ids", ())),
            variable_evolution_source_cycle_id=(
                str(value["variable_evolution_source_cycle_id"])
                if value.get("variable_evolution_source_cycle_id") is not None
                else None
            ),
            config=value.get("config", {}),
        )


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_name: str
    artifact_id: str
    schema_id: str | None
    schema_version: str | None
    content_hash: str
    legacy_content_hash: str | None
    lineage_id: str
    row_count: int
    quality_status: str
    compatibility_status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_id": self.artifact_id,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
            "legacy_content_hash": self.legacy_content_hash,
            "lineage_id": self.lineage_id,
            "row_count": self.row_count,
            "quality_status": self.quality_status,
            "compatibility_status": self.compatibility_status,
            "warnings": list(self.warnings),
        }
