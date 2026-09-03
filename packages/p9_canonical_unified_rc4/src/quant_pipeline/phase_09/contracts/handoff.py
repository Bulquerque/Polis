from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .artifacts import ArtifactSlot
from .base import BacktestId, CycleId, NonEmptyStr, RunId, SemanticVersion, StrictModel, UtcDateTime
from .integrity import IntegrityEnvelope
from .receipts import ModuleExecutionReceipt


class P8HandoffMode(StrEnum):
    FULL_V1 = "FULL_V1"
    P8_NATIVE_0_3_LIMITED = "P8_NATIVE_0_3_LIMITED"
    LEGACY_RC4_1_LIMITED = "LEGACY_RC4_1_LIMITED"


class CandidateTerminalCounts(StrictModel):
    received: int = Field(ge=0)
    selected: int = Field(ge=0)
    rejected: int = Field(ge=0)
    no_action: int = Field(ge=0)
    execution_failed: int = Field(ge=0)
    other_terminal: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> "CandidateTerminalCounts":
        terminal = (
            self.selected
            + self.rejected
            + self.no_action
            + self.execution_failed
            + self.other_terminal
        )
        if terminal != self.received:
            raise ValueError("candidate conservation failed")
        return self


class P8EvaluationHandoffPayload(StrictModel):
    contract_name: Literal["P8_EVALUATION_HANDOFF_V1"] = "P8_EVALUATION_HANDOFF_V1"
    contract_version: SemanticVersion = "1.0.0"
    mode: P8HandoffMode
    producer_package_version: NonEmptyStr
    run_id: RunId
    cycle_id: CycleId
    backtest_id: BacktestId
    published_at: UtcDateTime
    candidate_counts: CandidateTerminalCounts
    artifacts: tuple[ArtifactSlot, ...]
    p8_module_receipts: tuple[ModuleExecutionReceipt, ...]
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_unique_slots(self) -> "P8EvaluationHandoffPayload":
        roles = [slot.role for slot in self.artifacts]
        if len(roles) != len(set(roles)):
            raise ValueError("artifact roles must be unique")
        artifact_ids = [
            slot.reference.artifact_id
            for slot in self.artifacts
            if slot.reference is not None
        ]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact IDs must be unique within handoff")
        receipt_ids = [receipt.payload.module_id for receipt in self.p8_module_receipts]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError("P8 module receipts must have unique module IDs")
        return self

    def slot(self, role: str) -> ArtifactSlot | None:
        return next((slot for slot in self.artifacts if slot.role == role), None)


class P8EvaluationHandoffV1(StrictModel):
    payload: P8EvaluationHandoffPayload
    integrity: IntegrityEnvelope
