"""Typed errors for P3.S5."""

class S5Error(Exception):
    """Base error for the subphase."""

class ContractError(S5Error):
    """Input or output violates a frozen contract."""

class ProviderError(S5Error):
    """Base provider boundary error."""

class RetryableProviderError(ProviderError):
    """Transient provider failure eligible for bounded retry."""

class NonRetryableProviderError(ProviderError):
    """Provider failure that must fail immediately."""

class ProviderOutputError(ProviderError):
    """Provider returned content that did not validate."""

class ForbiddenFieldError(ContractError):
    """A forbidden economic or future-looking field was detected."""
