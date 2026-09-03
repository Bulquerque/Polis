"""Stable facade for canonicalization and diversity services."""

from .archive import archive_coverage_report, select_representatives
from .canonicalization import (
    add_economic_fingerprints,
    add_payoff_fingerprints,
    canonicalize_candidates,
    canonicalize_candidates_with_remap,
    cluster_equivalence,
    relative_scale_records,
)

__all__ = (
    "add_economic_fingerprints",
    "add_payoff_fingerprints",
    "archive_coverage_report",
    "canonicalize_candidates",
    "canonicalize_candidates_with_remap",
    "cluster_equivalence",
    "relative_scale_records",
    "select_representatives",
)
