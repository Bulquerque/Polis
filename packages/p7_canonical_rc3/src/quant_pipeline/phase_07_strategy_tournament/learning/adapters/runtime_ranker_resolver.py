from __future__ import annotations
from ..domain.errors import fail
from ..ports import RuntimeRanker
from .declarative_linear_ranker import DeclarativeLinearRanker

SUPPORTED_IMPLEMENTATIONS = {
    "numpy_pairwise_linear_ranknet_v1",
    "numpy_pointwise_ridge_v1",
}

def resolve_ranker(implementation_id: str) -> RuntimeRanker:
    if implementation_id in SUPPORTED_IMPLEMENTATIONS:
        return DeclarativeLinearRanker(implementation_id=implementation_id)
    fail("P7_LTR_RUNTIME_IMPLEMENTATION_UNSUPPORTED", f"unsupported runtime implementation {implementation_id}")
