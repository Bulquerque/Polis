from __future__ import annotations

import json

from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import SearchSpaceState, SearchStrategy
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.experiment import ExperimentValidationInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.parameters import HyperparameterRegistryInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.search_space import SearchSpaceCompilationInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m01_experiment_validator import ExperimentSpecificationValidator
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m02_parameter_registry import HyperparameterSchemaRegistry
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m03_search_space_compiler import ConditionalSearchSpaceCompiler


def prerequisites(s2_request):
    v = ExperimentSpecificationValidator().validate(ExperimentValidationInput(
        specification=s2_request.specification, frozen_cohort=s2_request.s1_outputs.frozen_cohort,
        metric_registry=s2_request.metric_registry, capability_registry=s2_request.capability_registry,
        promotion_policy=s2_request.promotion_policy,
    )).validated
    r = HyperparameterSchemaRegistry().build(HyperparameterRegistryInput(
        validated_specification=v, phase_contracts=s2_request.phase_parameter_contracts,
        deprecations=s2_request.deprecation_registry,
    )).snapshot
    return v, r


def test_conditional_space_compiles_with_exact_cardinality(s2_request) -> None:
    v, r = prerequisites(s2_request)
    out = ConditionalSearchSpaceCompiler().compile(SearchSpaceCompilationInput(
        validated_specification=v, parameter_snapshot=r,
        declaration=s2_request.search_space_declaration,
    ))
    assert out.compiled_space is not None
    assert out.compiled_space.state in {SearchSpaceState.SPACE_COMPILED, SearchSpaceState.SPACE_COMPILED_WITH_WARNINGS}
    assert out.compiled_space.cardinality.exact_cardinality == 189
    assert out.compiled_space.constraint_graph.parameter_order.index("P8.optimizer.type") < out.compiled_space.constraint_graph.parameter_order.index("P8.optimizer.cvar_alpha")


def test_condition_cycle_is_rejected(s2_request) -> None:
    v, r = prerequisites(s2_request)
    raw = s2_request.search_space_declaration.model_dump(mode="json")
    next(d for d in raw["domains"] if d["parameter_id"] == "P8.optimizer.type")["active_when"] = [{"parent_parameter_id": "P8.optimizer.cvar_alpha", "operator": "EQUALS", "values": [0.95]}]
    declaration = type(s2_request.search_space_declaration).model_validate_json(json.dumps(raw))
    out = ConditionalSearchSpaceCompiler().compile(SearchSpaceCompilationInput(
        validated_specification=v, parameter_snapshot=r, declaration=declaration,
    ))
    assert out.compiled_space is not None
    assert out.compiled_space.state is SearchSpaceState.SPACE_INVALID
    assert "P9_S2_SPACE_CONDITION_CYCLE" in out.compiled_space.reason_codes


def test_grid_requires_finite_grid_points(s2_request) -> None:
    raw_spec = s2_request.specification.model_dump(mode="json")
    raw_spec["search_strategy"] = SearchStrategy.GRID
    spec = type(s2_request.specification).model_validate_json(json.dumps(raw_spec))
    v, r = prerequisites(s2_request.model_copy(update={"specification": spec}))
    raw = s2_request.search_space_declaration.model_dump(mode="json")
    raw["domains"][0]["discrete_values"] = []
    raw["domains"][0]["lower"] = 0.2
    raw["domains"][0]["upper"] = 0.8
    raw["domains"][0]["discrete_values"] = []
    raw["domains"][0]["lower"] = 0.2
    raw["domains"][0]["upper"] = 0.8
    raw["domains"][0]["grid_points"] = None
    declaration = type(s2_request.search_space_declaration).model_validate_json(json.dumps(raw))
    out = ConditionalSearchSpaceCompiler().compile(SearchSpaceCompilationInput(
        validated_specification=v, parameter_snapshot=r, declaration=declaration,
    ))
    assert out.compiled_space.state is SearchSpaceState.SPACE_INVALID
