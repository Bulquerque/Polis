"""Typed receipts and results for the P5/P6/P7 RC3 compatibility bridge.

The RC3 payloads are external legacy contracts. They are validated at the
boundary and transformed into native P8 contracts; the bridge never weakens
native P8 models or enables permissive parsing inside S1/S2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping

from pydantic import Field

from quant_pipeline.phase_08_contracts.base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.p5 import P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import P6CandidateEconomicPackageV1
from quant_pipeline.phase_08_contracts.p7 import P7RankingHandoffV1
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import BeliefRecord


class SourceArtifactAuditRecord(StrictModel):
    source_phase: Literal["P5", "P6", "P7"]
    source_release: NonEmptyStr
    source_artifact_id: NonEmptyStr
    source_artifact_type: NonEmptyStr
    source_schema_version: NonEmptyStr
    source_reported_hash: NonEmptyStr | None = None
    source_hash_field: NonEmptyStr | None = None
    wrapped_reference: ArtifactReference


class P567RC3AdaptationReceiptV1(StrictModel):
    receipt_id: NonEmptyStr
    contract_version: Literal["P567_RC3_TO_P8_ADAPTATION_RECEIPT_V1"]
    schema_version: Literal["1.0.0"]
    adapter_id: Literal["P8.P567_RC3.BRIDGE"]
    adapter_release: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: AwareDatetime
    computed_at: AwareDatetime
    source_p5_release: NonEmptyStr
    source_p6_release: NonEmptyStr
    source_p7_release: NonEmptyStr
    source_artifacts: tuple[SourceArtifactAuditRecord, ...]
    received_candidate_ids: tuple[NonEmptyStr, ...]
    ranked_candidate_ids: tuple[NonEmptyStr, ...]
    eligibility_blocked_candidate_ids: tuple[NonEmptyStr, ...]
    safety_blocked_candidate_ids: tuple[NonEmptyStr, ...]
    abstained_candidate_ids: tuple[NonEmptyStr, ...]
    transformations: tuple[NonEmptyStr, ...] = Field(min_length=1)
    warnings: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    content_sha256: SHA256Str


@dataclass(frozen=True, slots=True)
class P567RC3AdaptationResult:
    """In-memory native P8 publication generated from one RC3 chain result."""

    handoff: P7RankingHandoffV1
    handoff_bytes: bytes
    p5_bundles: Mapping[str, P5BeliefEvidenceBundleV1]
    p6_packages: Mapping[str, P6CandidateEconomicPackageV1]
    s3_beliefs: Mapping[str, BeliefRecord]
    artifact_bytes: Mapping[str, bytes]
    adaptation_receipt: P567RC3AdaptationReceiptV1
    adaptation_receipt_ref: ArtifactReference

    def build_artifact_store(self):
        """Return the canonical in-memory S1 artifact-store adapter."""

        from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters.memory import (
            InMemoryArtifactStore,
        )

        return InMemoryArtifactStore(dict(self.artifact_bytes))

    def artifact(self, reference: ArtifactReference) -> bytes:
        return self.artifact_bytes[reference.artifact_id]
