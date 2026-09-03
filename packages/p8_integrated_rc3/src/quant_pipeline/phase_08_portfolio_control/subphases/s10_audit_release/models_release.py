from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import Field, field_validator
from .models_common import ArtifactRef, AuditContext, StrictModel
from .models_qualification import QualificationDecision
from .models_handoff import P9EvaluationHandoff

class FileHashEntry(StrictModel):
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

class ReleaseEvidence(StrictModel):
    tests_passed: int = Field(ge=0)
    tests_failed: int = Field(ge=0)
    combined_coverage_percent: float = Field(ge=0, le=100)
    structure_gate_passed: bool
    clean_install_passed: bool
    clean_extraction_passed: bool
    deterministic_replay_passed: bool
    p9_consumer_passed: bool
    namespace_coexistence_passed: bool

class ReleasePublicationRequest(StrictModel):
    context: AuditContext
    package_name: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    release_root: str = Field(min_length=1)
    included_paths: tuple[str, ...]
    sealed_at: datetime
    qualification: QualificationDecision
    qualification_ref: ArtifactRef
    p9_handoff: P9EvaluationHandoff
    p9_handoff_ref: ArtifactRef
    evidence: ReleaseEvidence
    known_debts: tuple[str, ...] = ()
    dependency_components: tuple[str, ...] = ()
    @field_validator("sealed_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("sealed_at must be timezone-aware")
        return value

class ReleaseManifest(StrictModel):
    release_id: str = Field(min_length=1)
    package_name: str
    package_version: str
    sealed_at: datetime
    files: tuple[FileHashEntry, ...]
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    qualification_ref: ArtifactRef
    p9_handoff: P9EvaluationHandoff
    p9_handoff_ref: ArtifactRef
    known_debts: tuple[str, ...]

class P0QualificationHandoff(StrictModel):
    handoff_id: str = Field(min_length=1)
    context: AuditContext
    release_id: str
    qualification: QualificationDecision
    evidence: ReleaseEvidence
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    dependency_components: tuple[str, ...]
    production_promotion_allowed: Literal[False] = False

class ReleasePublicationResult(StrictModel):
    manifest: ReleaseManifest
    p0_handoff: P0QualificationHandoff
