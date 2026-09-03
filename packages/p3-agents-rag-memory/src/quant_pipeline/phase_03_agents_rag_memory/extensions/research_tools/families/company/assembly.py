"""Pure orchestration for the six P3.S38 modules."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .assembly_support import build_bundle_output, lineage_for, require_inputs
from .handlers import (
    build_analysis_bundle, build_guidance_valuation_bundle, build_profile_bundle, build_statement_bundle,
)
from .models import CompanyOperationReadinessPanel, HandlerBundleManifest
from .qualification import build_operation_mode_qualification, combine_company_tool_bundle
from .readiness import build_readiness_panel


def execute_m01(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    require_inputs(inputs, "P3.S38.M01", (
        "research_tool_extension_snapshot", "tool_operation_registry", "research_mode_registry",
        "research_data_boundary_bundle", "phase2_research_view_manifest", "company_readiness_policy_config",
    ))
    lineage = lineage_for("P3.S38.M01", inputs, "company.readiness.v1")
    panel = build_readiness_panel(view_manifest=inputs.get("phase2_research_view_manifest", {}), lineage=lineage)
    gaps = [r.model_dump(mode="json") for r in panel.records if r.status.value != "AVAILABLE"]
    report = {"schema_version": "p3.s38.v1", "gaps": gaps, "content_hash": content_hash(gaps)}
    return {"company_operation_readiness_panel": panel.model_dump(mode="json"), "company_data_gap_report": report}


def execute_m02(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    require_inputs(inputs, "P3.S38.M02", (
        "company_operation_readiness_panel", "research_data_boundary_bundle",
        "temporal_entity_resolution_service", "company_profile_policy_config",
    ))
    return build_bundle_output(
        inputs=inputs, module_id="P3.S38.M02", bundle_builder=build_profile_bundle,
        bundle_output_name="company_profile_filing_handler_bundle",
        report_output_name="company_profile_handler_qualification_report",
        report_payload={"network_access": False, "xbrl_parsing_runtime": False},
    )


def execute_m03(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    require_inputs(inputs, "P3.S38.M03", (
        "company_operation_readiness_panel", "research_data_boundary_bundle",
        "company_statement_policy_config", "statement_concept_mapping_registry",
    ))
    return build_bundle_output(
        inputs=inputs, module_id="P3.S38.M03", bundle_builder=build_statement_bundle,
        bundle_output_name="financial_statement_handler_bundle",
        report_output_name="statement_semantics_manifest",
        report_payload={"as_reported_preserved": True, "restatement_overwrite": False},
    )


def execute_m04(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    require_inputs(inputs, "P3.S38.M04", (
        "financial_statement_handler_bundle", "research_data_boundary_bundle",
        "company_formula_registry", "company_operation_readiness_panel",
    ))
    return build_bundle_output(
        inputs=inputs, module_id="P3.S38.M04", bundle_builder=build_analysis_bundle,
        bundle_output_name="earnings_quality_capital_allocation_handler_bundle",
        report_output_name="company_formula_registry_manifest",
        report_payload={"formula_version": "1.0.0", "universal_quality_score": False},
    )


def execute_m05(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    require_inputs(inputs, "P3.S38.M05", (
        "company_operation_readiness_panel", "research_data_boundary_bundle", "guidance_policy_config",
        "peer_authority_policy_config", "valuation_method_registry", "company_profile_filing_handler_bundle",
        "financial_statement_handler_bundle",
    ))
    return build_bundle_output(
        inputs=inputs, module_id="P3.S38.M05", bundle_builder=build_guidance_valuation_bundle,
        bundle_output_name="guidance_peers_valuation_handler_bundle",
        report_output_name="valuation_method_registry_manifest",
        report_payload={"target_price_authority": False, "explicit_assumptions_required": True},
    )


def execute_m06(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    require_inputs(inputs, "P3.S38.M06", (
        "company_profile_filing_handler_bundle", "financial_statement_handler_bundle",
        "earnings_quality_capital_allocation_handler_bundle", "guidance_peers_valuation_handler_bundle",
        "company_operation_readiness_panel", "company_contract_test_report", "company_leakage_test_report",
    ))
    lineage = lineage_for("P3.S38.M06", inputs, "company.bundle.qualify.v1")
    names = (
        "company_profile_filing_handler_bundle", "financial_statement_handler_bundle",
        "earnings_quality_capital_allocation_handler_bundle", "guidance_peers_valuation_handler_bundle",
    )
    bundles = tuple(HandlerBundleManifest.model_validate(inputs[name], strict=False) for name in names)
    tool_bundle = combine_company_tool_bundle(bundles=bundles, lineage=lineage)
    readiness = CompanyOperationReadinessPanel.model_validate(inputs["company_operation_readiness_panel"], strict=False)
    qualification = build_operation_mode_qualification(
        tool_bundle=tool_bundle, readiness=readiness, lineage=lineage,
        contract_report=inputs.get("company_contract_test_report", {}),
        leakage_report=inputs.get("company_leakage_test_report", {}),
    )
    evidence = {
        "schema_version": "p3.s38.v1", "producer_module_id": "P3.S38.M06",
        "bundle_hash": tool_bundle.bundle_hash, "qualification_hash": qualification.matrix_hash,
        "promotion_authority": "P0_ONLY",
    }
    evidence["content_hash"] = content_hash(evidence)
    return {
        "company_tool_handler_bundle": tool_bundle.model_dump(mode="json"),
        "company_operation_mode_qualification": qualification.model_dump(mode="json"),
        "company_qualification_evidence_package": evidence,
    }
