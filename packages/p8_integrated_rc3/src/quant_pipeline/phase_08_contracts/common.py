"""Common content-addressed references and receipts."""

from __future__ import annotations

from pydantic import Field

from .base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel
from .enums import ReceiptStatus


class ArtifactReference(StrictModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    schema_version: NonEmptyStr
    contract_version: NonEmptyStr
    content_sha256: SHA256Str
    available_at: AwareDatetime
    relationship_type: NonEmptyStr | None = None


class LineageEdge(StrictModel):
    parent_artifact_id: NonEmptyStr
    parent_content_sha256: SHA256Str
    relationship_type: NonEmptyStr
    parent_schema_version: NonEmptyStr
    parent_contract_version: NonEmptyStr


class ModuleReceipt(StrictModel):
    module_id: NonEmptyStr
    status: ReceiptStatus
    input_hashes: tuple[SHA256Str, ...] = Field(default_factory=tuple)
    output_hash: SHA256Str
    computed_at: AwareDatetime
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class ArtifactConsumptionReceipt(StrictModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    status: ReceiptStatus
    consumer_module_id: NonEmptyStr
    input_hash: SHA256Str
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
