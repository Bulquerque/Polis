from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .base import (
    CONTRACT_PACK_ID,
    CONTRACT_PACK_VERSION,
    ArtifactPointer,
    ArtifactStatus,
    ContractModel,
    LineageRecord,
    NonEmptyStr,
    RunIdentity,
    Sha256,
)


class FoundationRuntimeManifest(ContractModel):
    artifact_name: Literal["p3_foundation_runtime_manifest"] = "p3_foundation_runtime_manifest"
    schema_id: Literal["p3.integration.foundation_runtime_manifest.v2"] = (
        "p3.integration.foundation_runtime_manifest.v2"
    )
    schema_version: Literal["2.0.0"] = "2.0.0"
    contract_pack_id: Literal["P3_INTEGRATION_CONTRACT_PACK_V2"] = CONTRACT_PACK_ID
    contract_pack_version: Literal["2.0.0"] = CONTRACT_PACK_VERSION
    artifact_id: NonEmptyStr
    identity: RunIdentity
    governance_view_ref: ArtifactPointer
    population_view_ref: ArtifactPointer
    social_graph_view_ref: ArtifactPointer
    state_view_ref: ArtifactPointer
    knowledge_view_ref: ArtifactPointer
    memory_view_ref: ArtifactPointer
    tool_view_ref: ArtifactPointer
    prompt_bundle_ref: ArtifactPointer
    model_registry_ref: ArtifactPointer
    capabilities: tuple[NonEmptyStr, ...]
    status: ArtifactStatus
    degraded_capabilities: tuple[NonEmptyStr, ...] = ()
    blocking_reasons: tuple[NonEmptyStr, ...] = ()
    lineage: LineageRecord
    content_hash: Sha256

    @model_validator(mode="after")
    def readiness_consistent(self) -> "FoundationRuntimeManifest":
        if self.status in {ArtifactStatus.READY, ArtifactStatus.EMPTY_VALID} and (
            self.degraded_capabilities or self.blocking_reasons
        ):
            raise ValueError("ready manifest cannot contain degraded or blocking reasons")
        if self.status is ArtifactStatus.BLOCKED and not self.blocking_reasons:
            raise ValueError("BLOCKED manifest requires blocking reasons")
        for pointer in self.view_pointers:
            if pointer.available_at is not None and pointer.available_at > self.identity.as_of_time:
                raise ValueError(f"artifact {pointer.artifact_id} is newer than the run cutoff")
        return self

    @property
    def view_pointers(self) -> tuple[ArtifactPointer, ...]:
        return (
            self.governance_view_ref,
            self.population_view_ref,
            self.social_graph_view_ref,
            self.state_view_ref,
            self.knowledge_view_ref,
            self.memory_view_ref,
            self.tool_view_ref,
        )
