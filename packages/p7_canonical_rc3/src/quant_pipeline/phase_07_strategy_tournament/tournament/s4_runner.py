from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .modules.P7_S4_M01_scoring_policy_head_binding_compiler import run_module as run_m01
from .modules.P7_S4_M02_multi_head_score_engine import run_module as run_m02
from .modules.P7_S4_M03_interpretable_score_assembler import run_module as run_m03
from .modules.P7_S4_M04_score_decomposition_and_tournament_handoff_publisher import run_module as run_m04


from .runtime import ArtifactContext


MODULE_SEQUENCE = (
    (
        "P7.S4.M01",
        run_m01,
        (
            "pareto_frontier_panel",
            "factor_adjusted_metric_panel",
            "comparable_candidate_metric_panel",
            "candidate_comparison_group_panel",
            "scoring_policy_context",
        ),
    ),
    (
        "P7.S4.M02",
        run_m02,
        (
            "scoring_head_input_panel",
            "factor_adjusted_metric_panel",
            "comparable_candidate_metric_panel",
            "scoring_policy_receipt",
        ),
    ),
    (
        "P7.S4.M03",
        run_m03,
        ("scoring_head_panel", "scoring_policy_receipt", "pareto_frontier_panel"),
    ),
    (
        "P7.S4.M04",
        run_m04,
        (
            "interpretable_score_panel",
            "scoring_head_panel",
            "scoring_policy_receipt",
            "pareto_frontier_panel",
            "pareto_frontier_audit_report",
            "dominated_candidate_panel",
            "dominance_survivor_panel",
            "dominance_relation_panel",
            "factor_adjusted_metric_panel",
            "factor_exposure_panel",
            "comparable_candidate_metric_panel",
            "metric_semantics_audit_report",
            "factor_adjustment_audit_report",
        ),
    ),
)


def run_subphase(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    context = ArtifactContext.from_inputs(inputs)
    module_results: list[dict[str, Any]] = []
    for module_id, handler, required in MODULE_SEQUENCE:
        result = handler(context.select(required), config)
        context.publish(result["outputs"], module_id=module_id)
        module_results.append({key: value for key, value in result.items() if key != "outputs"})
    output_names = (
        "scoring_head_input_panel",
        "scoring_policy_receipt",
        "scoring_head_panel",
        "interpretable_score_panel",
        "score_decomposition_panel",
        "interpretable_tournament_audit_report",
        "interpretable_tournament_handoff_manifest",
    )
    return {
        "phase": "P7",
        "subphase": "P7.S4",
        "status": "PASS",
        "module_results": module_results,
        "outputs": {name: context.artifacts[name] for name in output_names},
    }
