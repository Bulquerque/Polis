from __future__ import annotations

from quant_pipeline.phase_09.contracts.lineage import LineageResolutionStatus
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m01_handoff_validator import (
    P8EvaluationHandoffValidator,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m02_lineage_resolver import (
    ImmutableLineageChainResolver,
    LineageResolutionPolicy,
)


def _validated(fixture):
    outcome = P8EvaluationHandoffValidator(
        compatibility=fixture.compatibility,
        module_registry=fixture.module_registry,
        schema_registry=fixture.schema_registry,
        artifact_store=fixture.store,
    ).validate(fixture.handoff)
    assert outcome.validated is not None
    return outcome.validated


def test_full_lineage_resolves_complete(full_fixture) -> None:
    result = ImmutableLineageChainResolver(full_fixture.store).resolve(
        _validated(full_fixture),
        LineageResolutionPolicy(),
    )
    assert result.graph is not None
    assert result.graph.status is LineageResolutionStatus.RESOLVED_COMPLETE
    assert result.graph.topological_order[0] == "node-P2"
    assert result.graph.topological_order[-1] == "node-P8"


def test_lineage_manifest_tampering_is_corrupt(full_fixture) -> None:
    validated = _validated(full_fixture)
    slot = validated.handoff.slot("lineage_manifest")
    assert slot is not None and slot.reference is not None
    full_fixture.store._objects[slot.reference.location] = b"{}"
    result = ImmutableLineageChainResolver(full_fixture.store).resolve(
        validated,
        LineageResolutionPolicy(),
    )
    assert result.graph is None
    assert result.gap_report.status is LineageResolutionStatus.CORRUPT


def test_required_phase_policy_can_make_gap_material(full_fixture) -> None:
    result = ImmutableLineageChainResolver(full_fixture.store).resolve(
        _validated(full_fixture),
        LineageResolutionPolicy(required_phase_ids=("P1", "P2", "P4", "P5", "P6", "P7", "P8")),
    )
    assert result.graph is not None
    assert result.graph.status is LineageResolutionStatus.INCOMPLETE_MATERIAL
    assert any(gap.gap_id == "missing-phase-P1" for gap in result.graph.gaps)
