from __future__ import annotations

import json

from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import BudgetState
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.budget import BudgetPlanningInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import S2Runner
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from datetime import UTC, datetime


def test_full_fixture_reserves_budget(result) -> None:
    plan = result.s2_outputs.budget_plan
    assert plan is not None
    assert plan.state in {BudgetState.BUDGET_RESERVED, BudgetState.BUDGET_LIMITED}
    assert plan.configuration_limit == 6
    assert plan.trial_execution_limit >= 48


def test_resource_capacity_can_block_plan(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["resource_capacity"]["max_memory_mb_per_trial"] = 128
    raw["budget_policy"]["estimated_memory_mb_per_trial"] = 4096
    req = type(s2_request).model_validate_json(json.dumps(raw))
    out = S2Runner(clock=FixedClock(datetime(2026,1,7,15,0,tzinfo=UTC))).run(req)
    assert out.s2_outputs.budget_plan is None
    assert out.s2_outputs.subphase_receipt.payload.status.value in {"UNAVAILABLE", "INVALID"}


def test_unsafe_fidelity_is_blocked(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["fidelity_levels"][0]["preserves_transaction_costs"] = False
    req = type(s2_request).model_validate_json(json.dumps(raw))
    out = S2Runner(clock=FixedClock(datetime(2026,1,7,15,0,tzinfo=UTC))).run(req)
    assert out.s2_outputs.budget_plan is None
    assert any("FIDELITY" in code for code in out.s2_outputs.subphase_receipt.payload.reason_codes)
