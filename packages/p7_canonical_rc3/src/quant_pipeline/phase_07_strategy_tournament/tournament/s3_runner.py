from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .modules.P7_S3_M01_candidate_metric_semantics_compiler import run_module as run_m01
from .modules.P7_S3_M02_option_factor_exposure_adjuster import run_module as run_m02
from .modules.P7_S3_M03_strict_dominance_filter import run_module as run_m03
from .modules.P7_S3_M04_pareto_frontier_builder import run_module as run_m04


from .runtime import ArtifactContext


MODULE_SEQUENCE = (
    (
        "P7.S3.M01",
        run_m01,
        (
            "runtime_foundation_handoff_manifest",
            "eligible_strategy_candidate_panel",
            "candidate_comparison_group_panel",
            "candidate_metric_source_panel",
            "ranking_policy_context",
            "runtime_foundation_audit_report",
        ),
        (),
    ),
    (
        "P7.S3.M02",
        run_m02,
        (
            "comparable_candidate_metric_panel",
            "eligible_strategy_candidate_panel",
            "ranking_policy_context",
            "runtime_foundation_audit_report",
        ),
        ("option_factor_model_artifact",),
    ),
    (
        "P7.S3.M03",
        run_m03,
        (
            "factor_adjusted_metric_panel",
            "comparable_candidate_metric_panel",
            "candidate_comparison_group_panel",
            "ranking_policy_context",
            "runtime_foundation_audit_report",
        ),
        (),
    ),
    (
        "P7.S3.M04",
        run_m04,
        (
            "dominance_relation_panel",
            "dominated_candidate_panel",
            "dominance_survivor_panel",
            "factor_adjusted_metric_panel",
            "ranking_policy_context",
            "runtime_foundation_audit_report",
        ),
        (),
    ),
)


def run_subphase(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    context = ArtifactContext.from_inputs(inputs)
    module_results: list[dict[str, Any]] = []
    for module_id, handler, required, optional in MODULE_SEQUENCE:
        result = handler(context.select(required, optional), config)
        context.publish(result["outputs"], module_id=module_id)
        module_results.append({key: value for key, value in result.items() if key != "outputs"})
    output_names = (
        "comparable_candidate_metric_panel",
        "metric_semantics_audit_report",
        "factor_exposure_panel",
        "factor_adjusted_metric_panel",
        "factor_adjustment_audit_report",
        "dominance_relation_panel",
        "dominated_candidate_panel",
        "dominance_survivor_panel",
        "pareto_frontier_panel",
        "pareto_frontier_audit_report",
    )
    return {
        "phase": "P7",
        "subphase": "P7.S3",
        "status": "PASS",
        "module_results": module_results,
        "outputs": {name: context.artifacts[name] for name in output_names},
    }
