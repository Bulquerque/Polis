"""Deterministic runners for the implemented Foundation subphases P7.S1 and P7.S2."""

from __future__ import annotations

from pydantic import JsonValue

from .modules.P7_S1_M01_phase6_handoff_contract_validator import run_module as run_m01
from .modules.P7_S1_M02_candidate_artifact_reconciliation_engine import run_module as run_m02
from .modules.P7_S1_M03_temporal_integrity_and_forbidden_field_firewall import run_module as run_m03
from .modules.P7_S1_M04_promoted_ranking_feedback_loader import run_module as run_m04


def run_subphase_s1(
    *,
    phase6_manifest: dict[str, JsonValue],
    phase6_artifacts: list[dict[str, JsonValue]],
    module_config: dict[str, JsonValue],
    ranking_feedback_report: dict[str, JsonValue] | None = None,
    ranking_feedback_manifest: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    m01 = run_m01(
        {
            "phase7_strategy_handoff_manifest": phase6_manifest,
            "declared_p6_artifacts": phase6_artifacts,
        },
        module_config,
    )
    m02 = run_m02(
        {"verified_p6_artifact_index": m01["outputs"]["verified_p6_artifact_index"]},
        module_config,
    )
    m03 = run_m03(
        {"validated_strategy_candidate_bundle": m02["outputs"]["validated_strategy_candidate_bundle"]},
        module_config,
    )
    m04 = run_m04(
        {
            "ranking_feedback_report": ranking_feedback_report,
            "ranking_feedback_manifest": ranking_feedback_manifest,
        },
        module_config,
    )
    return {
        "P7.S1.M01": m01,
        "P7.S1.M02": m02,
        "P7.S1.M03": m03,
        "P7.S1.M04": m04,
        "outputs": {
            "verified_p6_artifact_index": m01["outputs"]["verified_p6_artifact_index"],
            "temporally_safe_candidate_bundle": m03["outputs"]["temporally_safe_candidate_bundle"],
            "ranking_feedback_context": m04["outputs"]["ranking_feedback_context"],
        },
    }



def run_subphase_s2(
    *,
    temporally_safe_candidate_bundle: dict[str, JsonValue],
    ranking_feedback_context: dict[str, JsonValue],
    eligibility_policy_registry: dict[str, JsonValue],
    comparison_group_policy: dict[str, JsonValue],
    metric_semantics_registry: dict[str, JsonValue],
    objective_family_registry: dict[str, JsonValue],
    module_config: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    m01 = _run_s2_eligibility(
        temporally_safe_candidate_bundle, ranking_feedback_context, eligibility_policy_registry, module_config
    )
    m02 = _run_s2_groups(m01, comparison_group_policy, module_config)
    m03 = _run_s2_metrics(m01, m02, metric_semantics_registry, objective_family_registry, module_config)
    m04 = _run_s2_handoff(m01, m02, m03, ranking_feedback_context, module_config)
    return {
        "P7.S2.M01": m01,
        "P7.S2.M02": m02,
        "P7.S2.M03": m03,
        "P7.S2.M04": m04,
        "outputs": {
            "eligible_strategy_candidate_panel": m01["outputs"]["eligible_strategy_candidate_panel"],
            "eligibility_blocked_candidate_panel": m01["outputs"]["eligibility_blocked_candidate_panel"],
            "eligibility_decision_panel": m01["outputs"]["eligibility_decision_panel"],
            "candidate_comparison_group_panel": m02["outputs"]["candidate_comparison_group_panel"],
            "candidate_metric_route_panel": m03["outputs"]["candidate_metric_route_panel"],
            "runtime_foundation_handoff_manifest": m04["outputs"]["runtime_foundation_handoff_manifest"],
        },
    }


def _run_s2_eligibility(bundle, feedback, registry, config):
    from .modules.P7_S2_M01_eligibility_policy_engine import run_module
    return run_module({
        "temporally_safe_candidate_bundle": bundle,
        "ranking_feedback_context": feedback,
        "eligibility_policy_registry": registry,
    }, config)


def _run_s2_groups(m01, policy, config):
    from .modules.P7_S2_M02_comparison_group_builder import run_module
    return run_module({
        "eligible_strategy_candidate_panel": m01["outputs"]["eligible_strategy_candidate_panel"],
        "comparison_group_policy": policy,
    }, config)


def _run_s2_metrics(m01, m02, metrics, objectives, config):
    from .modules.P7_S2_M03_metric_semantics_router import run_module
    return run_module({
        "eligible_strategy_candidate_panel": m01["outputs"]["eligible_strategy_candidate_panel"],
        "candidate_comparison_group_panel": m02["outputs"]["candidate_comparison_group_panel"],
        "metric_semantics_registry": metrics,
        "objective_family_registry": objectives,
    }, config)


def _run_s2_handoff(m01, m02, m03, feedback, config):
    from .modules.P7_S2_M04_runtime_foundation_handoff_publisher import run_module
    return run_module({
        "eligible_strategy_candidate_panel": m01["outputs"]["eligible_strategy_candidate_panel"],
        "eligibility_blocked_candidate_panel": m01["outputs"]["eligibility_blocked_candidate_panel"],
        "eligibility_decision_panel": m01["outputs"]["eligibility_decision_panel"],
        "candidate_comparison_group_panel": m02["outputs"]["candidate_comparison_group_panel"],
        "candidate_metric_route_panel": m03["outputs"]["candidate_metric_route_panel"],
        "ranking_feedback_context": feedback,
    }, config)
