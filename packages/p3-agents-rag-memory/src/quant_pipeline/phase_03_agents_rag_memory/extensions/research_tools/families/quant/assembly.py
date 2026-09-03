"""Pure orchestration functions for the four canonical P3.S39 modules."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.contracts.execution import ModuleExecutionContext

from .assembly_support import build_bundle_output, lineage_for
from .handlers import build_dependence_entropy_bundle, build_event_scenario_bundle, build_return_risk_bundle
from .models import HandlerBundleManifest
from .qualification import (
    build_operation_mode_qualification,
    combine_quant_tool_bundle,
    validate_qualification_report,
)


def execute_m01(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    policy = inputs.get("quant_method_policy_config", {})
    annualization = inputs.get("frequency_annualization_registry", {})
    return build_bundle_output(
        inputs=inputs,
        module_id="P3.S39.M01",
        bundle_builder=build_return_risk_bundle,
        bundle_output_name="return_risk_volatility_handler_bundle",
        manifest_output_name="return_volatility_method_manifest",
        manifest_payload={
            "method_policy_hash": content_hash(policy),
            "annualization_registry_hash": content_hash(annualization),
            "adaptive_window_selection": False,
            "signal_authority": False,
        },
    )


def execute_m02(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    dependence = inputs.get("dependence_method_policy_config", {})
    entropy = inputs.get("entropy_discretization_registry", {})
    return build_bundle_output(
        inputs=inputs,
        module_id="P3.S39.M02",
        bundle_builder=build_dependence_entropy_bundle,
        bundle_output_name="dependence_entropy_handler_bundle",
        manifest_output_name="dependence_entropy_method_manifest",
        manifest_payload={
            "dependence_policy_hash": content_hash(dependence),
            "entropy_registry_hash": content_hash(entropy),
            "lag_search_authority": False,
            "discretization_frozen": True,
        },
    )


def execute_m03(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    policy = inputs.get("event_scenario_method_policy_config", {})
    return build_bundle_output(
        inputs=inputs,
        module_id="P3.S39.M03",
        bundle_builder=build_event_scenario_bundle,
        bundle_output_name="event_window_scenario_handler_bundle",
        manifest_output_name="event_scenario_method_manifest",
        manifest_payload={
            "method_policy_hash": content_hash(policy),
            "causal_claim_authority": False,
            "scenario_probability_authority": False,
            "optimization_authority": False,
        },
    )


def execute_m04(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    lineage = lineage_for("P3.S39.M04", inputs, "quant.bundle.qualify.v1")
    names = (
        "return_risk_volatility_handler_bundle",
        "dependence_entropy_handler_bundle",
        "event_window_scenario_handler_bundle",
    )
    bundles = tuple(HandlerBundleManifest.model_validate(inputs[name], strict=False) for name in names)
    tool_bundle = combine_quant_tool_bundle(bundles=bundles, lineage=lineage)
    contract_report = inputs.get("quant_contract_test_report", {})
    property_report = inputs.get("quant_property_test_report", {})
    leakage_report = inputs.get("quant_leakage_test_report", {})
    qualification = build_operation_mode_qualification(
        tool_bundle=tool_bundle,
        lineage=lineage,
        contract_report=contract_report,
        property_report=property_report,
        leakage_report=leakage_report,
    )
    evidence = {
        "schema_version": "p3.s39.v1",
        "producer_module_id": "P3.S39.M04",
        "bundle_hash": tool_bundle.bundle_hash,
        "qualification_hash": qualification.matrix_hash,
        "contract_test_report_hash": content_hash(contract_report),
        "property_test_report_hash": content_hash(property_report),
        "leakage_test_report_hash": content_hash(leakage_report),
        "qualification_report_validation": {
            "contract": list(validate_qualification_report(contract_report, label="CONTRACT")),
            "property": list(validate_qualification_report(property_report, label="PROPERTY")),
            "leakage": list(validate_qualification_report(leakage_report, label="LEAKAGE")),
        },
        "forbidden_authorities_verified": True,
        "promotion_authority": "P0_ONLY",
    }
    evidence["content_hash"] = content_hash(evidence)
    return {
        "quant_tool_handler_bundle": tool_bundle.model_dump(mode="json"),
        "quant_operation_mode_qualification": qualification.model_dump(mode="json"),
        "quant_qualification_evidence_package": evidence,
    }
