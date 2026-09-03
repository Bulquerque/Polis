"""Typed error hierarchy for P8.S1."""

from __future__ import annotations


class P8S1Error(Exception):
    """Base class for all S1 failures."""

    reason_code = "P8_S1_ERROR"


class IntegrityError(P8S1Error):
    reason_code = "INTEGRITY_ERROR"


class ContractIntegrityError(IntegrityError):
    reason_code = "CONTRACT_INTEGRITY_ERROR"


class TemporalIntegrityError(IntegrityError):
    reason_code = "TEMPORAL_INTEGRITY_ERROR"


class HashMismatchError(IntegrityError):
    reason_code = "HASH_MISMATCH"


class LineageIntegrityError(IntegrityError):
    reason_code = "LINEAGE_INTEGRITY_ERROR"


class CandidateConservationError(IntegrityError):
    reason_code = "CANDIDATE_CONSERVATION_ERROR"


class StateInvariantError(IntegrityError):
    reason_code = "STATE_INVARIANT_ERROR"


class ConfigurationError(P8S1Error):
    reason_code = "CONFIGURATION_ERROR"


class CapabilityError(P8S1Error):
    reason_code = "CAPABILITY_ERROR"


class ExternalSystemError(P8S1Error):
    reason_code = "EXTERNAL_SYSTEM_ERROR"


class FeedbackAuthorizationError(IntegrityError):
    reason_code = "FEEDBACK_AUTHORIZATION_ERROR"


class FeedbackOutOfBoundsError(IntegrityError):
    reason_code = "FEEDBACK_OUT_OF_BOUNDS"
