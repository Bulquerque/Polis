"""Integrated public surface for P8 Agent 1 (S1 + S2)."""

from .api import (
    Agent1Policy,
    Agent1Ports,
    Agent1RunRequest,
    Agent1RunResult,
    run_agent1,
)
from .contracts import Agent1IntegrationReceiptV1

__all__ = [
    "Agent1IntegrationReceiptV1",
    "Agent1Policy",
    "Agent1Ports",
    "Agent1RunRequest",
    "Agent1RunResult",
    "run_agent1",
]

__version__ = "0.1.0"
