class S6Error(Exception):
    """Base error for P8.S6."""


class IntegrityError(S6Error):
    """Contract, hash, lineage or temporal integrity failure."""


class ContractIntegrityError(IntegrityError):
    pass


class TemporalIntegrityError(IntegrityError):
    pass


class PolicyIntegrityError(IntegrityError):
    pass


class RiskComputationError(S6Error):
    pass


class LifecycleCapabilityError(S6Error):
    pass


class SolverAdapterError(S6Error):
    pass
