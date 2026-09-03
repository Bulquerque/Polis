
"""Typed failure hierarchy for P8.S2."""

class P8S2Error(Exception):
    reason_code = "P8_S2_ERROR"


class IntegrityError(P8S2Error):
    reason_code = "INTEGRITY_ERROR"


class InputBundleIntegrityError(IntegrityError):
    reason_code = "S2_INPUT_BUNDLE_INTEGRITY_ERROR"


class CandidateNormalizationError(IntegrityError):
    reason_code = "CANDIDATE_NORMALIZATION_ERROR"


class GraphIntegrityError(IntegrityError):
    reason_code = "GRAPH_INTEGRITY_ERROR"


class EquivalenceIntegrityError(IntegrityError):
    reason_code = "EQUIVALENCE_INTEGRITY_ERROR"


class NettingIntegrityError(IntegrityError):
    reason_code = "NETTING_INTEGRITY_ERROR"


class StaticUniverseIntegrityError(IntegrityError):
    reason_code = "STATIC_UNIVERSE_INTEGRITY_ERROR"


class OrdinalSemanticsError(IntegrityError):
    reason_code = "ORDINAL_SEMANTICS_ERROR"


class ConfigurationError(P8S2Error):
    reason_code = "CONFIGURATION_ERROR"
