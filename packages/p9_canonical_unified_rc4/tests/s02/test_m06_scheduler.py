from __future__ import annotations

import json

from datetime import UTC, datetime

from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import SearchStrategy, TrialState
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import S2Runner


def execute(s2_request):
    return S2Runner(clock=FixedClock(datetime(2026,1,7,15,0,tzinfo=UTC))).run(s2_request)


def test_random_plan_assigns_all_slots(result) -> None:
    plan = result.s2_outputs.trial_plan
    assert plan is not None
    assert len(plan.slots) == 48
    assert all(slot.configuration_id is not None for slot in plan.slots)
    assert all(slot.initial_state is TrialState.PLANNED for slot in plan.slots)
    assert len({slot.idempotency_key for slot in plan.slots}) == len(plan.slots)


def test_state_ledger_covers_exactly_plan(result) -> None:
    plan = result.s2_outputs.trial_plan
    ledger = result.s2_outputs.trial_state_ledger
    assert {s.trial_id for s in plan.slots} == {r.trial_id for r in ledger.records}


def test_successive_halving_reserves_future_rungs(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["specification"]["search_strategy"] = SearchStrategy.SUCCESSIVE_HALVING
    raw["early_stopping_policy"] = {"enabled": True, "signal_metric_ids": ["competition.score"], "minimum_completed_cells": 1, "development_only": True}
    raw["fidelity_levels"] = [
        {"fidelity_id":"low","ordinal":0,"resource_fraction":"0.25","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
        {"fidelity_id":"full","ordinal":1,"resource_fraction":"1","preserves_transaction_costs":True,"preserves_lifecycle":True,"preserves_temporal_order":True},
    ]
    out = execute(type(s2_request).model_validate_json(json.dumps(raw)))
    plan = out.s2_outputs.trial_plan
    assert plan is not None
    assert any(slot.initial_state is TrialState.RESERVED for slot in plan.slots)
    assert all(slot.configuration_id is None for slot in plan.slots if slot.initial_state is TrialState.RESERVED)


def test_worker_memory_limit_blocks_scheduler(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["worker_capabilities"]["max_memory_mb_per_trial"] = 128
    out = execute(type(s2_request).model_validate_json(json.dumps(raw)))
    assert out.s2_outputs.trial_plan is None
