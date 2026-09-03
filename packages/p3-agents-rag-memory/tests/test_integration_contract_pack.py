from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import (
    FoundationGovernanceView,
    PopulationRuntimeView,
    ReadinessStatus,
    SocialGraphRuntimeView,
)


def _load_text(root: Path, name: str) -> str:
    return (root / "fixtures/integration_contract_pack" / f"{name}.json").read_text(encoding="utf-8")


def test_population_projection_preserves_weights_seeds_and_has_no_activation_policy(root: Path) -> None:
    view = PopulationRuntimeView.model_validate_json(_load_text(root, "population_runtime_view"), strict=True)
    assert abs(sum(record.representation_weight for record in view.records) - 1.0) < 1e-8
    assert all(record.deterministic_seed >= 0 for record in view.records)
    serialized = view.model_dump(mode="json")
    assert "activation_profile" not in json.dumps(serialized)


def test_social_graph_projection_preserves_all_runtime_semantics(root: Path) -> None:
    view = SocialGraphRuntimeView.model_validate_json(_load_text(root, "social_graph_runtime_view"), strict=True)
    assert view.records
    edge = view.records[0]
    assert edge.strength == edge.interaction_frequency
    assert edge.domain_trust
    assert edge.global_trust >= 0
    assert edge.provenance_ref


def test_contracts_reject_extra_fields(root: Path) -> None:
    payload = json.loads(_load_text(root, "foundation_governance_view"))
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        FoundationGovernanceView.model_validate(payload, strict=True)


def test_empty_valid_is_distinct() -> None:
    assert ReadinessStatus.EMPTY_VALID != ReadinessStatus.SKIPPED_NOT_APPLICABLE
