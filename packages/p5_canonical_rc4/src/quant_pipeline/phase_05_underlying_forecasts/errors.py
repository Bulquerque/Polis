"""Stable and semantically specific error taxonomy for the P5 phase."""
from __future__ import annotations

from enum import StrEnum


class ReasonCode(StrEnum):
    P4_HASH_MISMATCH = "P5_P4_HASH_MISMATCH"
    VIEW_FILTER_UNMATCHED = "P5_VIEW_FILTER_UNMATCHED"
    DUPLICATE_VIEW = "P5_DUPLICATE_VIEW"
    DUPLICATE_GRAIN = "P5_DUPLICATE_GRAIN"
    FUTURE_INFORMATION = "P5_FUTURE_INFORMATION"
    CALENDAR_UNAVAILABLE = "P5_CALENDAR_UNAVAILABLE"
    TARGET_UNAVAILABLE = "P5_TARGET_UNAVAILABLE"
    INSUFFICIENT_HISTORY = "P5_INSUFFICIENT_HISTORY"
    MODEL_CAPABILITY_UNAVAILABLE = "P5_MODEL_CAPABILITY_UNAVAILABLE"
    MODEL_FAILED_BASELINE_GATE = "P5_MODEL_FAILED_BASELINE_GATE"
    MODEL_NOT_CALIBRATED = "P5_MODEL_NOT_CALIBRATED"
    NO_OOF_EVIDENCE = "P5_NO_OOF_EVIDENCE"
    QUANTILE_CROSSING = "P5_QUANTILE_CROSSING"
    COVARIANCE_NOT_PSD = "P5_COVARIANCE_NOT_PSD"
    COVARIANCE_UNSTABLE = "P5_COVARIANCE_UNSTABLE"
    SCENARIO_MASS_INVALID = "P5_SCENARIO_MASS_INVALID"
    SCENARIO_DEPENDENCE_INVALID = "P5_SCENARIO_DEPENDENCE_INVALID"
    LIQUIDITY_INPUT_UNAVAILABLE = "P5_LIQUIDITY_INPUT_UNAVAILABLE"
    SEVERE_OOD = "P5_SEVERE_OOD"
    REGIME_UNSTABLE = "P5_REGIME_UNSTABLE"
    CONFIDENCE_UNCALIBRATED = "P5_CONFIDENCE_UNCALIBRATED"
    LINEAGE_UNMAPPED = "P5_LINEAGE_UNMAPPED"
    MANIFEST_REFERENCE_INVALID = "P5_MANIFEST_REFERENCE_INVALID"
    INPUT_MUTATION_DETECTED = "P5_INPUT_MUTATION_DETECTED"
    CONTRACT_INVALID = "P5_CONTRACT_INVALID"
    MISSING_INPUT = "P5_MISSING_INPUT"
    ACTION_NOT_ALLOWED = "P5_ACTION_NOT_ALLOWED"
    EXECUTION_MODE_INVALID = "P5_EXECUTION_MODE_INVALID"
    ARTIFACT_INTEGRITY_INVALID = "P5_ARTIFACT_INTEGRITY_INVALID"
    NUMERICAL_FAILURE = "P5_NUMERICAL_FAILURE"
    DATA_QUALITY_INVALID = "P5_DATA_QUALITY_INVALID"
    TRAINING_FAILED = "P5_TRAINING_FAILED"
    QUALIFICATION_FAILED = "P5_QUALIFICATION_FAILED"


class P5Error(Exception):
    """Base exception carrying a stable machine-readable code."""

    code = "P5-UNEXPECTED-001"

    def __init__(self, message: str, *, reason_code: ReasonCode | str | None = None) -> None:
        super().__init__(message)
        if reason_code is not None:
            self.reason_code = str(reason_code)
        else:
            self.reason_code = None


class ContractError(P5Error):
    code = "P5-CONTRACT-001"


class UnknownModuleError(ContractError):
    code = "P5-MODULE-UNKNOWN"


class MissingInputError(ContractError):
    code = "P5-CONTRACT-002"


class ActionNotAllowedError(ContractError):
    code = "P5-CONTRACT-003"


class ExecutionModeError(ContractError):
    code = "P5-CONTRACT-004"


class ArtifactError(P5Error):
    code = "P5-ARTIFACT-001"


class ArtifactIntegrityError(ArtifactError):
    code = "P5-ARTIFACT-002"


class NumericalError(P5Error):
    code = "P5-NUMERICAL-001"


class DataQualityError(P5Error):
    code = "P5-DATA-001"


class LeakageError(DataQualityError):
    code = "P5-DATA-002"


class TemporalIntegrityError(LeakageError):
    """Fatal point-in-time violation that must never degrade to availability loss."""

    code = "P5-DATA-003"


class CapabilityUnavailableError(P5Error):
    code = "P5-CAPABILITY-001"


class TrainingError(P5Error):
    code = "P5-TRAINING-001"


class QualificationError(P5Error):
    code = "P5-QUALIFICATION-001"
