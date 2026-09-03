"""Curated public contracts for P9.S1.

Specialized models remain available from their explicit submodules to keep the
public API small and prevent accidental dependency on implementation details.
"""

from .artifacts import ArtifactAbsenceState, ArtifactReference, ArtifactSlot
from .base import Availability, EvidenceClass, ModuleStatus, StrictModel
from .handoff import (
    CandidateTerminalCounts,
    P8EvaluationHandoffPayload,
    P8EvaluationHandoffV1,
    P8HandoffMode,
)
from .integrity import (
    CANONICALIZATION_VERSION,
    HASH_ALGORITHM,
    IntegrityEnvelope,
    canonical_json_bytes,
    payload_sha256,
    sha256_bytes,
    verify_integrity,
)
from .receipts import (
    ConsumerReceipt,
    ConsumerReceiptPayload,
    ModuleExecutionReceipt,
    ModuleExecutionReceiptPayload,
    SubphaseExecutionReceipt,
    SubphaseExecutionReceiptPayload,
)
from .s1 import S1ExecutionOutputs

__all__ = [
    "ArtifactAbsenceState",
    "ArtifactReference",
    "ArtifactSlot",
    "Availability",
    "CANONICALIZATION_VERSION",
    "CandidateTerminalCounts",
    "ConsumerReceipt",
    "ConsumerReceiptPayload",
    "EvidenceClass",
    "HASH_ALGORITHM",
    "IntegrityEnvelope",
    "ModuleExecutionReceipt",
    "ModuleExecutionReceiptPayload",
    "ModuleStatus",
    "P8EvaluationHandoffPayload",
    "P8EvaluationHandoffV1",
    "P8HandoffMode",
    "S1ExecutionOutputs",
    "StrictModel",
    "SubphaseExecutionReceipt",
    "SubphaseExecutionReceiptPayload",
    "canonical_json_bytes",
    "payload_sha256",
    "sha256_bytes",
    "verify_integrity",
]
