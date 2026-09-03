"""Anti-cycle ports used by stress and reduction modules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .arrays import ScenarioSet


@dataclass(frozen=True, slots=True)
class DecisionEvaluation:
    first_action: tuple[float, ...]
    objective: float
    risk_metrics: dict[str, float]
    constraint_violations: tuple[str, ...] = ()


class DecisionEvaluationPort(Protocol):
    def evaluate(self, scenario_set: ScenarioSet) -> DecisionEvaluation:
        """Evaluate a fixed decision problem against a scenario set."""


@dataclass(frozen=True, slots=True)
class RiskResponse:
    loss: float
    margin: float
    liquidity: float
    failure_states: tuple[str, ...]


class RiskResponseEvaluatorPort(Protocol):
    def evaluate(self, shock_vector: tuple[float, ...]) -> RiskResponse:
        """Evaluate a scaled stress shock."""
