from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quant_pipeline.phase_08_portfolio_control.agent3_integration import (
    parse_lifecycle_context_json,
    parse_risk_bundle_json,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.api import run_s5
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.domain.target import (
    first_action_delta_map,
    first_horizon_target_portfolio,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.enums import LifecycleStatus
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.modules.lifecycle_engine import run_module

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 3, 18, 0, 1, tzinfo=timezone.utc)


def test_unchanged_first_horizon_position_remains_visible_to_lifecycle() -> None:
    risk = parse_risk_bundle_json((ROOT / "fixtures/risk_bundle.json").read_bytes())
    context = parse_lifecycle_context_json((ROOT / "fixtures/s6_context.json").read_bytes())
    result = run_s5(risk, processing_time=NOW)

    no_delta_plan = result.payload.mpc_plan.model_copy(update={"first_actions": ()})
    retained = result.model_copy(
        update={"payload": result.payload.model_copy(update={"mpc_plan": no_delta_plan})}
    )

    assert first_action_delta_map(retained) == {}
    assert first_horizon_target_portfolio(retained) == {"C1": 5.0}

    lifecycle = run_module(
        risk,
        retained,
        context.payload.lifecycle_candidates,
        context.payload.policy_context.lifecycle,
        NOW,
    )
    assert lifecycle.status is LifecycleStatus.SUPPORTED
