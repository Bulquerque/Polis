from __future__ import annotations


class P8Error(Exception):
    """Base error for P8 integrity and implementation failures."""


class ContractIntegrityError(P8Error):
    pass


class TemporalIntegrityError(P8Error):
    pass


class AuthorizationError(P8Error):
    pass


class CapabilityError(P8Error):
    pass


class StateTransitionError(P8Error):
    pass


class OverfillError(StateTransitionError):
    pass


class ReconciliationError(P8Error):
    pass


class UnsupportedMappingError(P8Error):
    pass
