class RuntimeAssuranceError(Exception):
    """Base typed error for P8.S9."""


class ContractIntegrityError(RuntimeAssuranceError):
    """Input does not satisfy a closed contract."""


class TemporalIntegrityError(RuntimeAssuranceError):
    """Observation or policy violates time ordering."""


class StateInvariantError(RuntimeAssuranceError):
    """Runtime state is internally impossible or inconsistent."""


class ShadowAuthorityError(RuntimeAssuranceError):
    """A shadow policy attempted to gain execution authority."""
