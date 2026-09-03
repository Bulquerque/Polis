"""Diagnostic-only assessment for the legacy RC4.1 P7 handoff surface.

RC4.1 does not carry enough information to create the new handoff without
fabricating semantic values. This module therefore reports gaps and never
synthesizes a P7RankingHandoffV1.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LegacyCompatibilityReport:
    mode: str
    missing_semantics: tuple[str, ...]
    forbidden_defaults_detected: tuple[str, ...]


_REQUIRED_NEW_SEMANTICS = (
    "canonical_candidate_id",
    "comparison_group_id",
    "score_semantics",
    "p6_economic_package_ref",
    "decision_trace_ref",
    "separate eligibility_blocked/safety_blocked/abstained populations",
    "content-addressed artifact references",
)

_FORBIDDEN_DEFAULT_FIELDS = (
    "score_confidence",
    "liquidity_score",
    "expiration",
    "strike",
    "created_at",
)


def assess_legacy_rc41_bundle(bundle: Mapping[str, object]) -> LegacyCompatibilityReport:
    ranked_rows = bundle.get("ranked_candidate_panel", ())
    detected: set[str] = set()
    if isinstance(ranked_rows, Sequence) and not isinstance(ranked_rows, (str, bytes, bytearray)):
        for row in ranked_rows:
            if isinstance(row, Mapping):
                for field in _FORBIDDEN_DEFAULT_FIELDS:
                    if field in row:
                        detected.add(field)
    return LegacyCompatibilityReport(
        mode="LOSSY_UNSUPPORTED",
        missing_semantics=_REQUIRED_NEW_SEMANTICS,
        forbidden_defaults_detected=tuple(sorted(detected)),
    )
