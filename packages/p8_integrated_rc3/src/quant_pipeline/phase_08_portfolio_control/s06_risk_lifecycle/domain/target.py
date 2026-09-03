from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.enums import DiscreteStatus


def target_paths(bundle: S5ResultBundle) -> dict[str, tuple[float, ...]]:
    return {x.candidate_id: x.quantities_by_horizon for x in bundle.payload.discrete_target.quantities}


def first_horizon_target_portfolio(bundle: S5ResultBundle) -> dict[str, float]:
    """Complete candidate portfolio at the first MPC horizon.

    Unlike ``first_actions``, this includes unchanged positions. Hedge,
    lifecycle and emergency modules must reason about the whole retained book.
    """
    return {
        item.candidate_id: item.quantities_by_horizon[0]
        for item in bundle.payload.discrete_target.quantities
    }


def first_action_delta_map(bundle: S5ResultBundle) -> dict[str, float]:
    return {x.candidate_id: x.delta_quantity for x in bundle.payload.mpc_plan.first_actions}


def first_action_current_quantity_map(bundle: S5ResultBundle) -> dict[str, float]:
    return {x.candidate_id: x.current_quantity for x in bundle.payload.mpc_plan.first_actions}


# Backward-compatible alias. New code must choose the full target or action map
# explicitly instead of relying on this ambiguous name.
def first_targets(bundle: S5ResultBundle) -> dict[str, float]:
    return first_horizon_target_portfolio(bundle)


def is_no_action(bundle: S5ResultBundle) -> bool:
    return bundle.payload.discrete_target.status == DiscreteStatus.NO_ACTION_VALID
