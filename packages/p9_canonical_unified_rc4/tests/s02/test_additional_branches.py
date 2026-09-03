from __future__ import annotations

import json
from datetime import UTC, datetime

from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import (
    CatalogState,
    ModuleStatus,
    SearchStrategy,
    TrialPlanState,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.configuration import ConfigurationBuildInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.trials import TrialSchedulingInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m05_configuration_builder import ConfigurationIdentityAndLineageBuilder
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m06_trial_scheduler import HyperparameterTrialSchedulerAndStateReconciler
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import S2Runner


def execute(request):
    return S2Runner(clock=FixedClock(datetime(2026, 1, 7, 15, 0, tzinfo=UTC))).run(request)


def parse_like(request, raw):
    return type(request).model_validate_json(json.dumps(raw))


def test_grid_strategy_executes_grid_branch(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["specification"]["search_strategy"] = SearchStrategy.GRID
    out = execute(parse_like(s2_request, raw))
    assert out.s2_outputs.configuration_catalog is not None
    assert all(c.source == "GRID" for c in out.s2_outputs.configuration_catalog.configurations)


def test_hyperband_builds_multiple_brackets(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["specification"]["search_strategy"] = SearchStrategy.HYPERBAND
    raw["specification"]["requested_max_configurations"] = 9
    raw["budget_policy"]["maximum_configurations"] = 9
    raw["budget_policy"]["maximum_trial_executions"] = 1000
    raw["budget_policy"]["maximum_total_cpu_seconds"] = 10000
    raw["resource_capacity"]["max_total_cpu_seconds"] = 10000
    raw["early_stopping_policy"] = {
        "enabled": True,
        "signal_metric_ids": ["competition.score"],
        "minimum_completed_cells": 1,
        "development_only": True,
    }
    raw["fidelity_levels"] = [
        {"fidelity_id":"quarter","ordinal":0,"resource_fraction":"0.25","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
        {"fidelity_id":"half","ordinal":1,"resource_fraction":"0.5","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
        {"fidelity_id":"full","ordinal":2,"resource_fraction":"1","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
    ]
    out = execute(parse_like(s2_request, raw))
    plan = out.s2_outputs.trial_plan
    assert plan is not None
    assert len({slot.bracket_id for slot in plan.slots}) >= 2
    assert any(slot.configuration_id is None for slot in plan.slots)


def test_configuration_hash_collision_is_blocked(result, s2_request) -> None:
    build_input = ConfigurationBuildInput(
        compiled_search_space=result.s2_outputs.compiled_search_space,
        parameter_snapshot=result.s2_outputs.parameter_snapshot,
        budget_plan=result.s2_outputs.budget_plan,
        identity_context=s2_request.identity_context,
    )
    out = ConfigurationIdentityAndLineageBuilder(hash_function=lambda _: "0" * 64).build(build_input)
    assert out.catalog is not None
    assert out.catalog.state is CatalogState.IDENTITY_COLLISION
    assert "P9_S2_CONFIG_ID_COLLISION" in out.catalog.reason_codes


def test_scheduler_rejects_empty_catalog(result, s2_request) -> None:
    empty = result.s2_outputs.configuration_catalog.model_copy(update={"configurations": ()})
    scheduling_input = TrialSchedulingInput(
        validated_specification=result.s2_outputs.validated_specification,
        configuration_catalog=empty,
        budget_plan=result.s2_outputs.budget_plan,
        compiled_search_space=result.s2_outputs.compiled_search_space,
        scheduler_policy=s2_request.scheduler_policy,
        worker_capabilities=s2_request.worker_capabilities,
        seed_policy=s2_request.seed_policy,
    )
    out = HyperparameterTrialSchedulerAndStateReconciler().schedule(scheduling_input)
    assert out.trial_plan is None
    assert out.report.state is TrialPlanState.SCHEDULER_INFEASIBLE


def test_unknown_capability_and_compensable_guardrail_block(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["specification"]["required_capability_ids"] = ["missing.capability"]
    out = execute(parse_like(s2_request, raw))
    assert out.s2_outputs.module_receipts[0].payload.status is ModuleStatus.UNAVAILABLE

    raw = s2_request.model_dump(mode="json")
    raw["promotion_policy"]["hard_guardrails_non_compensable"] = False
    out = execute(parse_like(s2_request, raw))
    assert out.s2_outputs.module_receipts[0].payload.status is ModuleStatus.INVALID


def test_missing_full_fidelity_and_early_stop_signal_are_blocked(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["specification"]["search_strategy"] = SearchStrategy.SUCCESSIVE_HALVING
    raw["early_stopping_policy"] = {
        "enabled": True,
        "signal_metric_ids": ["competition.score"],
        "minimum_completed_cells": 1,
        "development_only": True,
    }
    raw["fidelity_levels"] = [
        {"fidelity_id":"quarter","ordinal":0,"resource_fraction":"0.25","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
        {"fidelity_id":"half","ordinal":1,"resource_fraction":"0.5","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
    ]
    out = execute(parse_like(s2_request, raw))
    assert out.s2_outputs.budget_plan is None
    assert "P9_S2_FIDELITY_FULL_LEVEL_MISSING" in out.s2_outputs.module_receipts[3].payload.reason_codes
