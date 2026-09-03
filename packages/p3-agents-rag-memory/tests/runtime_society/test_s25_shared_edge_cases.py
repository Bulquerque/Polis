from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_03_agents_rag_memory.s25.common import (
    canonical_value,
    clamp,
    lineage_id,
    require_effective_cycle,
    require_same_context,
)
from quant_pipeline.phase_03_agents_rag_memory.s25.entrypoints import prepare_inputs
from quant_pipeline.phase_03_agents_rag_memory.s25.errors import (
    S25ContractError,
    S25PolicyError,
    S25TemporalError,
)
from quant_pipeline.phase_03_agents_rag_memory.s25.types import (
    RelationshipUpdateConfig,
    SocialGraphConfig,
    reject_forbidden_policy_keys,
)

pytestmark = pytest.mark.unit


class _ExampleEnum(StrEnum):
    A = "A"


class _Context:
    def __init__(self, run_id: str, cycle_id: int, as_of_time: datetime) -> None:
        self.run_id = run_id
        self.cycle_id = cycle_id
        self.as_of_time = as_of_time


def test_canonical_helpers_reject_unsafe_values() -> None:
    with pytest.raises(S25TemporalError):
        canonical_value(datetime(2026, 1, 1))
    with pytest.raises(S25ContractError):
        canonical_value(float("nan"))
    assert canonical_value(_ExampleEnum.A) == "A"
    assert canonical_value({"b", "a"}) == ["a", "b"]


def test_clamp_and_lineage_fail_closed() -> None:
    with pytest.raises(S25ContractError):
        clamp(0.5, 1.0, 0.0)
    with pytest.raises(S25ContractError):
        lineage_id("P3.S25.M01", "output", [])


def test_context_and_cycle_guards_detect_mismatch() -> None:
    aware = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    with pytest.raises(S25ContractError):
        require_same_context()
    with pytest.raises(S25ContractError):
        require_same_context(_Context("r1", 1, aware), _Context("r2", 1, aware))
    with pytest.raises(S25TemporalError):
        require_effective_cycle(2, current_cycle=1, label="event")


def test_prepare_inputs_supports_legacy_config_and_rejects_non_mapping() -> None:
    result = prepare_inputs(
        module_id="P3.S25.M01",
        inputs={"a": 1},
        required=("a", "config"),
        config_key="config",
        config={"version": "v1"},
    )
    assert result["config"] == {"version": "v1"}
    with pytest.raises(S25ContractError):
        prepare_inputs(
            module_id="P3.S25.M01",
            inputs=[],  # type: ignore[arg-type]
            required=(),
            config_key="config",
            config=None,
        )
    with pytest.raises(S25ContractError):
        prepare_inputs(
            module_id="P3.S25.M01",
            inputs={},
            required=("required",),
            config_key="config",
            config=None,
        )


def test_relationship_update_config_rejects_inconsistent_domains(config_fixture) -> None:
    config = config_fixture("RELATIONSHIP_UPDATE_CONFIG.yaml")
    config["domain_weights"].pop(next(iter(config["domain_weights"])))
    with pytest.raises(ValidationError):
        RelationshipUpdateConfig.model_validate(config)


def test_social_graph_config_rejects_invalid_range(config_fixture) -> None:
    config = config_fixture("SOCIAL_GRAPH_CONFIG.yaml")
    config["domain_trust_range"] = [0.8, 0.2]
    with pytest.raises(ValidationError):
        SocialGraphConfig.model_validate(config)


def test_retro_policy_rejects_named_person_in_value() -> None:
    with pytest.raises(S25PolicyError):
        reject_forbidden_policy_keys({"note": "target_person_id=p3"})
