"""Final material safety gate without economic recomputation."""
from __future__ import annotations

from datetime import timedelta
from math import isfinite

from ...boundary.config import SafetyPolicy
from ...domain.models import Candidate, SafetyOutcome


def evaluate_safety(candidate: Candidate, adjusted_score: float | None, policy: SafetyPolicy, upstream_reasons: tuple[str, ...]) -> SafetyOutcome:
    reasons = list(upstream_reasons)
    evidence = [candidate.strategy_artifact_id]
    if adjusted_score is None or not isfinite(adjusted_score):
        reasons.append("P7_NON_FINITE_SCORE")
    if not candidate.context_available or not candidate.strategy_artifact_id or not candidate.strategy_content_sha256:
        reasons.append("P7_MISSING_STRATEGY_CONTEXT")
    if candidate.defined_risk_status not in policy.accepted_defined_risk_statuses:
        reasons.append("P7_UPSTREAM_DEFINED_RISK_INVALID")
    if candidate.decision_time - candidate.execution_context_time > timedelta(seconds=policy.max_execution_context_age_seconds):
        reasons.append("P7_STALE_EXECUTION_CONTEXT")
    if candidate.execution_context_time > candidate.decision_time:
        reasons.append("P7_STALE_EXECUTION_CONTEXT")
    if candidate.model_promotion_status not in policy.accepted_model_promotion_statuses:
        reasons.append("P7_MODEL_NOT_PROMOTED")
    if candidate.model_compatibility_status not in policy.accepted_model_compatibility_statuses:
        reasons.append("P7_MODEL_INCOMPATIBLE")
    if candidate.ood_severity in policy.severe_ood_values:
        reasons.append("P7_SEVERE_OOD_BLOCK_POLICY")
    normalized = tuple(sorted(set(reasons)))
    return SafetyOutcome(candidate.candidate_id, bool(normalized), normalized, tuple(sorted(set(evidence))))
