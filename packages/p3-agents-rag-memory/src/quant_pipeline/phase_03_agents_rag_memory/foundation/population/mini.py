"""Config-driven laboratory profile for a genuinely small P3 society.

The canonical production population remains unchanged. This helper applies an
explicit profile to the same S5-S8 pipeline so a three-person society can be
run end-to-end without embedding test-only overrides in code.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .orchestration import PopulationPipelineRequest
from .s6.models import PairwiseTagCell, TagCoverageRequirement


def apply_mini_profile(
    request: PopulationPipelineRequest,
    profile: Mapping[str, Any],
) -> PopulationPipelineRequest:
    """Return a profile-driven request for a small, non-production society."""

    if profile.get("mode") != "laboratory_only":
        raise ValueError("mini society profile must be laboratory_only")
    target = int(profile.get("target_population_size", 0))
    if target < 3:
        raise ValueError("mini profile must target at least three people")
    coverage = dict(profile.get("coverage", {}))
    if "tag_coverage_requirements" in coverage:
        coverage["tag_coverage_requirements"] = tuple(
            item if isinstance(item, TagCoverageRequirement) else TagCoverageRequirement.model_validate(item)
            for item in coverage["tag_coverage_requirements"]
        )
    if "pairwise_tag_cells" in coverage:
        coverage["pairwise_tag_cells"] = tuple(
            item if isinstance(item, PairwiseTagCell) else PairwiseTagCell.model_validate(item)
            for item in coverage["pairwise_tag_cells"]
        )
    representation = dict(profile.get("representation", {}))
    graph = dict(profile.get("social_graph", {}))
    prior_generation = request.generation_request.prior_population_generation_state.model_copy(
        update={
            "missing_coverage_cells": tuple(profile.get("missing_coverage_cells", ())),
            "density_targets": tuple(profile.get("density_targets", ())),
        }
    )
    generation = request.generation_request.model_copy(
        update={
            "prior_population_generation_state": prior_generation,
            "population_generation_config": request.generation_request.population_generation_config.model_copy(
                update={
                    "requested_batch_size": target,
                    "required_role_families": tuple(profile["required_role_families"]),
                }
            )
        }
    )
    return replace(
        request,
        generation_request=generation,
        coverage_density_config=request.coverage_density_config.model_copy(
            update={
                "target_population_size": target,
                "required_role_families": tuple(profile["required_role_families"]),
                **{key: tuple(value) if key.endswith("requirements") or key.endswith("cells") else value for key, value in coverage.items()},
            }
        ),
        population_representation_config=request.population_representation_config.model_copy(
            update=representation
        ),
        social_graph_config=request.social_graph_config.model_copy(update=graph),
    )


def selected_candidate_indexes(profile: Mapping[str, Any]) -> tuple[int, ...]:
    indexes = tuple(int(value) for value in profile.get("candidate_indexes", ()))
    if indexes != tuple(range(len(indexes))):
        raise ValueError("mini profile must select a contiguous prefix of candidates")
    if not indexes:
        raise ValueError("mini profile must select at least one candidate")
    return indexes
