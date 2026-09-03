from __future__ import annotations
import pytest
from .population_support import build_population_pipeline


@pytest.mark.asyncio
async def test_population_pipeline_covers_s8(root, governance_outputs, operational_policy, objective_aliases):
    _, _, result = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    assert result.status.value == "READY"
    assert result.validated_candidates.accepted_candidates
    assert 0.0 <= result.coverage.personality_coverage_report.coverage.overall_coverage_ratio <= 1.0
    assert result.population_validation.validated_population_manifest.validation_status.value == "READY"
    assert result.social_graph_validation.validated_initial_social_graph.validation_status.value == "READY"
