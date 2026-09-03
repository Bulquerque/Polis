"""Compatibility re-export for all strict P3.S40 contracts."""
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .model_base import *  # noqa: F403
from .model_downstream import *  # noqa: F403
from .model_evidence import *  # noqa: F403


def hashed_model_payload(payload: object) -> str:
    return content_hash(payload)
