"""P6.S7 module implementations."""

from __future__ import annotations

from typing import Any

from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..domain.models import ScenarioProbabilityMassAuditRecord
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult
from .services import (
    cost_liquidity,
    greek_records,
    payoff_records,
    scenario_records,
    shape_records,
)
from .wave2_services import (
    ambiguity_records,
    merge_pathwise,
    pathwise_records,
)


def _artifact(
    records: tuple[Any, ...],
    name: str,
    module_id: str,
    context: PhaseContext,
    *,
    status=None,
    metadata=None,
):
    return build_artifact(
        artifact_type=name,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=records,
        status=status,
        metadata=metadata,
    )


def entry(inputs, context, configuration) -> ModuleResult:
    module_id = "P6.S7.M01"
    records = cost_liquidity(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["eligible_option_quote_panel"].records),
        tuple(inputs["validated_underlying_panel"].records),
        configuration,
    )
    artifact = _artifact(
        records,
        "strategy_cost_liquidity_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"strategy_cost_liquidity_panel": artifact},
    )


def payoff(inputs, context, configuration) -> ModuleResult:
    del configuration
    module_id = "P6.S7.M02"
    records = payoff_records(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["validated_underlying_panel"].records),
        tuple(inputs["strategy_cost_liquidity_panel"].records),
    )
    artifact = _artifact(
        records,
        "strategy_payoff_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"strategy_payoff_panel": artifact},
    )


def pathwise(inputs, context, configuration) -> ModuleResult:
    module_id = "P6.S7.M03"
    records = pathwise_records(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["validated_market_belief_state"].records),
        tuple(inputs["eligible_option_quote_panel"].records),
        tuple(inputs["strategy_cost_liquidity_panel"].records),
        configuration,
    )
    status = ArtifactStatus.COMPLETE if records else ArtifactStatus.EMPTY_VALID
    artifact = _artifact(
        records,
        "pathwise_valuation_panel",
        module_id,
        context,
        status=status,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"pathwise_valuation_panel": artifact},
    )


def greeks(inputs, context, configuration) -> ModuleResult:
    module_id = "P6.S7.M04"
    records = greek_records(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["eligible_option_quote_panel"].records),
        tuple(inputs["validated_underlying_panel"].records),
        configuration,
    )
    artifact = _artifact(
        records,
        "strategy_greek_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"strategy_greek_panel": artifact},
    )


def shapes(inputs, context, configuration) -> ModuleResult:
    del configuration
    module_id = "P6.S7.M05"
    records = shape_records(tuple(inputs["strategy_payoff_panel"].records))
    artifact = _artifact(
        records,
        "strategy_shape_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"strategy_shape_panel": artifact},
    )


def _scenario_mass_audit_payload(belief) -> dict[str, Any]:
    scenario_mass = sum((row.probability for row in belief.scenarios), 0)
    defaults = {
        "belief_state_id": belief.belief_state_id,
        "underlying_id": belief.underlying_id,
        "horizon_days": belief.horizon_days,
        "method": belief.scenario_source or "NATIVE_MARKET_BELIEF",
        "source_scenario_count": len(belief.scenarios),
        "retained_scenario_count": len(belief.scenarios),
        "original_probability_mass": scenario_mass,
        "retained_probability_mass": scenario_mass,
        "rejected_probability_mass": 0,
        "normalization_factor": 1 if belief.scenarios else None,
        "renormalized": False,
    }
    defaults.update(belief.scenario_mass_audit)
    return defaults


def scenarios(inputs, context, configuration) -> ModuleResult:
    del configuration
    module_id = "P6.S7.M06"
    records = scenario_records(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["validated_market_belief_state"].records),
        tuple(inputs["strategy_cost_liquidity_panel"].records),
    )
    records = merge_pathwise(
        records,
        tuple(inputs["pathwise_valuation_panel"].records),
    )
    status = ArtifactStatus.COMPLETE if records else ArtifactStatus.BLOCKED
    artifact = _artifact(
        records,
        "strategy_scenario_evaluation_panel",
        module_id,
        context,
        status=status,
        metadata={"scenario_capability_required": True},
    )
    beliefs = tuple(inputs["validated_market_belief_state"].records)
    mass_audits = tuple(
        ScenarioProbabilityMassAuditRecord.model_validate(_scenario_mass_audit_payload(belief))
        for belief in beliefs
    )
    mass_artifact = _artifact(
        mass_audits, "scenario_probability_mass_audit_panel", module_id, context,
        status=ArtifactStatus.COMPLETE if mass_audits else ArtifactStatus.EMPTY_VALID,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={
            "strategy_scenario_evaluation_panel": artifact,
            "scenario_probability_mass_audit_panel": mass_artifact,
        },
    )


def ambiguity(inputs, context, configuration) -> ModuleResult:
    module_id = "P6.S7.M07"
    records = ambiguity_records(
        tuple(inputs["strategy_scenario_evaluation_panel"].records),
        tuple(inputs["validated_market_belief_state"].records),
        tuple(inputs["raw_strategy_candidate_panel"].records),
        configuration,
    )
    available = records and any(
        item.status.value == "AVAILABLE"
        for item in records
    )
    status = ArtifactStatus.COMPLETE if available else ArtifactStatus.DEGRADED
    artifact = _artifact(
        records,
        "strategy_ambiguity_evaluation_panel",
        module_id,
        context,
        status=status,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"strategy_ambiguity_evaluation_panel": artifact},
    )
