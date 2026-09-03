"""Explicit compatibility projections; no version checks are scattered through the domain."""
from __future__ import annotations
from .models import PopulationGenerationStateV3
from ..s5.models import GenerationMode as S5GenerationMode, PriorPopulationGenerationState


def project_state_for_s5(state: PopulationGenerationStateV3) -> PriorPopulationGenerationState:
    """Project state v3 onto the exact P3.S5 v2 input surface.

    The orchestrator keeps v3 as the authoritative S6 state and passes only this projection
    to P3.S5.M01. This prevents loss of the accumulator while preserving S5 compatibility.
    """
    return PriorPopulationGenerationState(
        creator_run_id=state.creator_run_id,
        generation_round=state.generation_round,
        mode=S5GenerationMode(state.mode.value),
        accepted_candidate_ids=state.accepted_candidate_ids,
        missing_coverage_cells=state.missing_coverage_cells,
        density_targets=state.density_targets,
    )
