"""P6.S5 module implementations."""

from __future__ import annotations

from typing import Iterable

from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.results import ModuleResult
from .services import (
    estimate_market_implied_states,
    qualify_targets,
    regularize_targets,
    transform_beliefs_to_targets,
)


def _artifact(
    records: Iterable[object],
    name,
    module_id,
    context,
    *,
    status=None,
):
    return build_artifact(
        artifact_type=name,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=tuple(records),
        status=status,
    )


def implied(inputs, context, configuration):
    module_id = "P6.S5.M01"
    records = estimate_market_implied_states(
        tuple(inputs["validated_market_belief_state"].records),
        tuple(inputs["eligible_option_contract_panel"].records),
        tuple(inputs["eligible_option_quote_panel"].records),
        context.decision_time,
        configuration,
    )
    status = ArtifactStatus.COMPLETE if records else ArtifactStatus.EMPTY_VALID
    artifact = _artifact(
        records,
        "market_implied_state_panel",
        module_id,
        context,
        status=status,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"market_implied_state_panel": artifact},
    )


def transform(inputs, context, configuration):
    module_id = "P6.S5.M02"
    if not configuration.operational_mode.inverse_design_enabled:
        artifact = _artifact(
            (),
            "target_payoff_panel_raw",
            module_id,
            context,
            status=ArtifactStatus.EMPTY_VALID,
        )
        return ModuleResult(
            module_id=module_id,
            outputs={"target_payoff_panel_raw": artifact},
        )
    records = transform_beliefs_to_targets(
        tuple(inputs["validated_market_belief_state"].records),
        tuple(inputs["market_implied_state_panel"].records),
        tuple(inputs["validated_underlying_panel"].records),
        configuration,
    )
    artifact = _artifact(
        records,
        "target_payoff_panel_raw",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"target_payoff_panel_raw": artifact},
    )


def regularize(inputs, context, configuration):
    module_id = "P6.S5.M03"
    targets, reports = regularize_targets(
        tuple(inputs["target_payoff_panel_raw"].records),
        configuration,
    )
    outputs = {
        "target_payoff_panel": _artifact(
            targets,
            "target_payoff_panel",
            module_id,
            context,
        ),
        "target_payoff_regularization_report": _artifact(
            reports,
            "target_payoff_regularization_report",
            module_id,
            context,
        ),
    }
    return ModuleResult(module_id=module_id, outputs=outputs)


def qualify(inputs, context, configuration):
    module_id = "P6.S5.M04"
    records = qualify_targets(
        tuple(inputs["target_payoff_panel"].records),
        configuration,
    )
    artifact = _artifact(
        records,
        "target_payoff_qualification_report",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"target_payoff_qualification_report": artifact},
    )
