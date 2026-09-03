"""Public API for P9.S8 attribution and failure mining."""

from .bundle import (
    ProspectiveAttributionBundle,
    S8ExecutionRequest,
)
from .contracts import (
    AttributionQuality,
    CausalStrength,
    S8ConsumerReceipt,
    S8ModuleExecutionReceipt,
    S8SubphaseExecutionReceipt,
    S8UpstreamReferences,
)
from .runner import S8Pipeline

__all__ = [
    "ProspectiveAttributionBundle",
    "AttributionQuality",
    "CausalStrength",
    "S8ConsumerReceipt",
    "S8ExecutionRequest",
    "S8ModuleExecutionReceipt",
    "S8Pipeline",
    "S8SubphaseExecutionReceipt",
    "S8UpstreamReferences",
]
