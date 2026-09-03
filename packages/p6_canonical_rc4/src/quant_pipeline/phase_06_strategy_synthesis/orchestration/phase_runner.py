"""Single canonical P6 runner across the ten-subphase topology."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.context import PhaseContext
from ..subphase_01_boundary_market_snapshot.runner import run_subphase as run_s1
from ..subphase_02_canonical_strategy_domain.runner import run_subphase as run_s2
from ..subphase_03_template_generation.runner import run_subphase as run_s3
from ..subphase_04_mutation_deformation.runner import run_subphase as run_s4
from ..subphase_05_target_payoff.runner import run_subphase as run_s5
from ..subphase_06_inverse_design.runner import run_subphase as run_s6
from ..subphase_07_pricing_scenario_evaluation.runner import run_subphase as run_s7
from ..subphase_08_feasibility_defined_risk.runner import run_subphase as run_s8
from ..subphase_09_canonicalization_diversity.runner import run_subphase as run_s9
from ..subphase_10_qualification_publication.runner import run_subphase as run_s10

_CANONICAL_NAMES = (
    "strategy_candidate_panel",
    "strategy_leg_panel",
    "strategy_market_snapshot",
    "p5_handoff_compatibility_report",
    "strategy_payoff_panel",
    "strategy_scenario_evaluation_panel",
    "strategy_ambiguity_evaluation_panel",
    "strategy_greek_panel",
    "strategy_risk_panel",
    "strategy_cost_liquidity_panel",
    "strategy_lineage_panel",
    "strategy_generation_trace_panel",
    "candidate_equivalence_panel",
    "quality_diversity_archive",
    "candidate_rejection_report",
    "candidate_generation_audit",
    "phase7_strategy_handoff_manifest",
    "target_payoff_panel",
    "target_payoff_qualification_report",
    "mutation_application_panel",
    "solver_result_panel",
    "pathwise_valuation_panel",
    "quality_diversity_report",
)

_LEGACY_P7_NAMES = (
    "candidate_feature_base_panel",
    "candidate_universe_panel",
    "option_instrument_feature_panel",
    "contract_existence_report",
    "option_feature_quality_report",
    "candidate_generation_log",
    "phase7_candidate_handoff_manifest",
)


def run_phase(
    inputs: Mapping[str, Any],
    configuration: Mapping[str, Any] | Phase6RunConfiguration,
) -> dict[str, Any]:
    """Run the complete P6 path for the selected bounded operational mode."""
    config = _configuration(configuration)
    context = PhaseContext.from_configuration(config)
    state: dict[str, Any] = dict(inputs)
    subphases = _run_all_subphases(state, context, config)
    return _phase_result(state, subphases, config)


def _configuration(value) -> Phase6RunConfiguration:
    return value if isinstance(value, Phase6RunConfiguration) else Phase6RunConfiguration.model_validate(value)


def _run_all_subphases(state, context, configuration) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for runner in (run_s1, run_s2, run_s3, run_s4, run_s5, run_s6):
        result = runner(state, context, configuration)
        state.update(result.outputs)
        results[result.subphase_id] = result
    state["template_strategy_candidate_panel"] = state["raw_strategy_candidate_panel"]
    state["template_generation_trace_panel"] = state["strategy_generation_trace_panel"]
    state["raw_strategy_candidate_panel"] = state["synthesized_strategy_candidate_panel"]
    state["strategy_generation_trace_panel"] = (
        state["synthesized_generation_trace_panel"]
    )
    for runner in (run_s7, run_s8, run_s9, run_s10):
        result = runner(state, context, configuration)
        state.update(result.outputs)
        results[result.subphase_id] = result
    return results


def _phase_result(state, subphases, configuration) -> dict[str, Any]:
    public_outputs = {
        key: value
        for key, value in state.items()
        if hasattr(value, "artifact_id")
    }
    advanced = configuration.operational_mode.value != "TEMPLATE_ONLY"
    return {
        "phase_id": "P6",
        "phase_name": "payoff_design_strategy_synthesis_candidate_generation",
        "target_release": "P6-RC6.2-P5-V2-CLOSURE-RC4",
        "operational_mode": configuration.operational_mode.value,
        "completed_subphases": tuple(f"P6.S{i}" for i in range(1, 11)),
        "operational_path": (
            tuple(f"P6.S{i}" for i in range(1, 11))
            if advanced
            else (
                "P6.S1",
                "P6.S2",
                "P6.S3",
                "P6.S7",
                "P6.S8",
                "P6.S9",
                "P6.S10",
            )
        ),
        "subphases": subphases,
        "outputs": public_outputs,
        "canonical_outputs": {
            name: state[name]
            for name in _CANONICAL_NAMES
        },
        "phase7_outputs": {
            name: state[name]
            for name in _LEGACY_P7_NAMES
            if name in state
        },
        "production_promotion_allowed": False,
    }
