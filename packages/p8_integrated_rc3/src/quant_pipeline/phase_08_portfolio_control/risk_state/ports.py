"""Anti-cycle ports for optional execution and broker integrations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExecutionRiskEstimate:
    fill_probability: float
    partial_fill_risk: float
    legging_risk: float
    impact_cost: float
    quality_status: str
    reason_codes: tuple[str, ...] = ()


class ExecutionRiskEstimatorPort(Protocol):
    def estimate(self, candidate_id: str, capacity_units: float) -> ExecutionRiskEstimate:
        """Return a qualified pretrade execution-risk estimate."""


@dataclass(frozen=True, slots=True)
class BrokerMarginEstimate:
    candidate_id: str
    margin_per_unit: float
    quality_status: str
    reason_codes: tuple[str, ...] = ()


class BrokerMarginEstimatorPort(Protocol):
    def estimate_margin(self, candidate_id: str) -> BrokerMarginEstimate:
        """Return an exact or broker-qualified margin estimate."""
