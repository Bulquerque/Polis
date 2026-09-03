"""Typed failures for P3.S25.

Errors are intentionally narrow so the parent P3 runner can map them to the
reason codes declared in the module contracts without parsing message text.
"""

from __future__ import annotations


class S25Error(RuntimeError):
    """Base error for Trust & Relationship Evolution."""


class S25ContractError(S25Error):
    """An input or output violated a declared schema or module contract."""


class S25TemporalError(S25ContractError):
    """An artifact or event violated point-in-time or cycle semantics."""


class S25LineageError(S25ContractError):
    """Required lineage or causal identity was missing or inconsistent."""


class S25PolicyError(S25ContractError):
    """A relationship policy or Retro patch exceeded its authority."""


class S25TopologyError(S25ContractError):
    """The resulting social graph violated a topology invariant."""
