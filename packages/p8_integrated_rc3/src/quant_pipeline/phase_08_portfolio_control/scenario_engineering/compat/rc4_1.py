"""Explicit limited adapter for legacy RC4.1 belief records."""
from __future__ import annotations

from datetime import datetime

from ..contracts import ArtifactRef, BeliefRecord, DistributionType, HorizonSpec, HorizonUnit, ProbabilityMeasure
from ..errors import CapabilityUnavailableError, ContractIntegrityError

ADAPTER_ID = "P5_RC4_1_LIMITED_COMPATIBILITY_ADAPTER"


def adapt_rc4_1_belief(record: dict, resolved_payload, content_sha256: str) -> BeliefRecord:
    """Adapt only when the referenced distribution payload has been independently resolved.

    The adapter intentionally refuses to construct a normal distribution from expected return
    and volatility fields alone.
    """
    if resolved_payload is None:
        raise CapabilityUnavailableError(
            "RC4.1 distribution identifiers are insufficient; resolved payload is required"
        )
    required = {"belief_state_id", "target_id", "forecast_horizon_hours", "available_at", "decision_time"}
    missing = required.difference(record)
    if missing:
        raise ContractIntegrityError(f"missing legacy fields: {sorted(missing)}")
    horizon = HorizonSpec(value=int(record["forecast_horizon_hours"]), unit=HorizonUnit.HOURS)
    return BeliefRecord(
        belief_state_id=str(record["belief_state_id"]), target_id=str(record["target_id"]),
        factor_ids=tuple(record.get("factor_ids", (record["target_id"],))),
        distribution_type=DistributionType(resolved_payload.kind.upper()),
        probability_measure=ProbabilityMeasure(record.get("probability_measure", "PHYSICAL")),
        forecast_horizon=horizon, holding_horizon=horizon, evaluation_horizon=horizon,
        payload=resolved_payload,
        calibration_score=record.get("calibration_score"), ood_score=record.get("ood_score"),
        disagreement_score=record.get("disagreement_score"), regime_id=record.get("regime_id"),
        available_at=datetime.fromisoformat(record["available_at"]),
        decision_time=datetime.fromisoformat(record["decision_time"]),
        source_ref=ArtifactRef(artifact_id=ADAPTER_ID, content_sha256=content_sha256),
    )
