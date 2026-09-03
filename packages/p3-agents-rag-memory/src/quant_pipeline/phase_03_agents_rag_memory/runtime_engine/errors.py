from __future__ import annotations


class RuntimeIntegrationError(RuntimeError):
    """Base error for explicit runtime integration failures."""


class ContractTranslationError(RuntimeIntegrationError):
    """Raised when a legacy artifact cannot be translated without inventing data."""


class CycleIdentityError(ContractTranslationError):
    """Raised when an integer legacy cycle index cannot be resolved safely."""


class BoundaryValidationError(RuntimeIntegrationError):
    """Raised when a producer output violates the canonical boundary contract."""


class OptionalDependencyUnavailable(RuntimeIntegrationError):
    """Raised only when an explicitly requested optional capability is unavailable."""
