"""Explicit S7 orchestration without dynamic discovery."""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .modules import (
    P7_S7_M01_candidate_similarity_graph_builder as m01,
    P7_S7_M02_diversity_adjustment_engine as m02,
    P7_S7_M03_final_candidate_safety_gate as m03,
    P7_S7_M04_abstention_and_rankability_gate as m04,
)

MODULE_ORDER = (m01, m02, m03, m04)


def run_s7(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context: dict[str, object] = dict(inputs)
    receipts: list[object] = []
    for module in MODULE_ORDER:
        result = module.run_module(MappingProxyType(context), config)
        receipt = result.pop("module_execution_receipt")
        for artifact_name, artifact in result.items():
            if artifact_name in context:
                raise RuntimeError(f"P7_OUTPUT_OVERWRITE_FORBIDDEN: {artifact_name}")
            context[artifact_name] = artifact
        receipts.append(receipt)
    output_names = (
        "candidate_similarity_edge_panel",
        "candidate_similarity_summary_panel",
        "candidate_diversity_cluster_panel",
        "diversity_adjustment_panel",
        "diversity_adjusted_score_panel",
        "diversity_audit_report",
        "safety_eligible_candidate_panel",
        "safety_blocked_candidate_panel",
        "safety_gate_audit_report",
        "rankable_candidate_panel",
        "abstained_candidate_panel",
        "final_blocked_candidate_panel",
        "rankability_group_report",
        "rankability_handoff_manifest",
    )
    return {name: context[name] for name in output_names} | {"module_execution_receipts": receipts}



def run_s8(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    from .modules import (
        P7_S8_M01_deterministic_group_ranking_engine as s8_m01,
        P7_S8_M02_thesis_card_and_ranking_audit_builder as s8_m02,
        P7_S8_M03_phase8_strategy_ranking_handoff_builder as s8_m03,
    )
    context: dict[str, object] = dict(inputs)
    receipts: list[object] = []
    for module in (s8_m01, s8_m02, s8_m03):
        result = module.run_module(MappingProxyType(context), config)
        receipt_record = result.pop("module_execution_receipt")
        for artifact_name, artifact in result.items():
            if artifact_name in context:
                raise RuntimeError(f"P7_OUTPUT_OVERWRITE_FORBIDDEN: {artifact_name}")
            context[artifact_name] = artifact
        receipts.append(receipt_record)
    output_names = (
        "ranked_strategy_candidate_panel",
        "ranking_tie_report",
        "ranking_group_summary_panel",
        "strategy_thesis_card_panel",
        "ranking_trace_panel",
        "ranking_audit_report",
        "ranked_strategy_execution_context_snapshot",
        "compatibility_projection_report",
        "phase8_strategy_ranking_handoff_manifest",
    )
    return {name: context[name] for name in output_names} | {"module_execution_receipts": receipts}


def run_finalization_pipeline(
    learning_inputs: Mapping[str, object],
    s7_config: Mapping[str, object],
    s8_config: Mapping[str, object],
) -> dict[str, object]:
    s7_outputs = run_s7(learning_inputs, s7_config)
    s8_inputs = dict(learning_inputs)
    s8_inputs.update({name: value for name, value in s7_outputs.items() if name != "module_execution_receipts"})
    s8_outputs = run_s8(s8_inputs, s8_config)
    return {
        "s7": s7_outputs,
        "s8": s8_outputs,
        "module_execution_receipts": (
            *s7_outputs["module_execution_receipts"],
            *s8_outputs["module_execution_receipts"],
        ),
    }
