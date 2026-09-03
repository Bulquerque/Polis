from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

from quant_pipeline.phase_03_agents_rag_memory.contracts.execution import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.assembly import (
    execute_m01,
    execute_m02,
    execute_m03,
    execute_m04,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    QuantOperationModeQualification,
    QuantToolBundle,
)


def qualification_report(label: str, passed: int) -> dict[str, object]:
    evidence_payload = {"contract": label, "executed_cases": passed}
    report: dict[str, object] = {
        "status": "PASS",
        "executed": passed,
        "passed": passed,
        "evidence_id": f"s39-test-{label}",
        "lineage_id": f"s39-lineage-{label}",
        "evidence_payload": evidence_payload,
        "evidence_hash": content_hash(evidence_payload),
    }
    report["report_hash"] = content_hash(report)
    return report


@pytest.mark.asyncio
async def test_module_assembly_produces_seven_unique_operations() -> None:
    context = ModuleExecutionContext()
    shared = {
        "research_data_boundary_bundle": {"bundle_id": "boundary-1"},
        "tool_operation_registry": {"version": "1.0.0"},
        "research_mode_registry": {"version": "1.0.0"},
    }
    m01 = execute_m01(
        {
            **shared,
            "quant_method_policy_config": {"version": "1.0.0"},
            "frequency_annualization_registry": {"DAILY": 252},
        },
        context,
    )
    m02 = execute_m02(
        {
            **shared,
            "dependence_method_policy_config": {"version": "1.0.0"},
            "entropy_discretization_registry": {"version": "1.0.0"},
        },
        context,
    )
    m03 = execute_m03(
        {
            **shared,
            "event_scenario_method_policy_config": {"version": "1.0.0"},
        },
        context,
    )
    m04 = execute_m04(
        {
            "return_risk_volatility_handler_bundle": m01["return_risk_volatility_handler_bundle"],
            "dependence_entropy_handler_bundle": m02["dependence_entropy_handler_bundle"],
            "event_window_scenario_handler_bundle": m03["event_window_scenario_handler_bundle"],
            "quant_contract_test_report": qualification_report("contract", 10),
            "quant_property_test_report": qualification_report("property", 5),
            "quant_leakage_test_report": qualification_report("leakage", 6),
        },
        context,
    )
    bundle = QuantToolBundle.model_validate(m04["quant_tool_handler_bundle"], strict=False)
    matrix = QuantOperationModeQualification.model_validate(m04["quant_operation_mode_qualification"], strict=False)
    assert len(bundle.handlers) == 7
    assert len({item.operation_id for item in bundle.handlers}) == 7
    assert len(matrix.records) == 21
    assert all(record.status.value == "QUALIFIED_LOCAL" for record in matrix.records)


def test_generated_schemas_are_valid() -> None:
    root = Path(__file__).resolve().parents[5]
    schemas = sorted((root / "contracts" / "extensions" / "research_tools" / "schemas" / "families" / "quant").glob("*.schema.json"))
    assert len(schemas) == 16
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)

@pytest.mark.asyncio
async def test_public_module_wrappers_match_declared_outputs() -> None:
    from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules.P3_S39_M01_return_risk_volatility_handler_bundle_builder import execute as run_m01
    from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules.P3_S39_M02_dependence_entropy_handler_bundle_builder import execute as run_m02
    from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules.P3_S39_M03_event_window_scenario_handler_bundle_builder import execute as run_m03
    context = ModuleExecutionContext()
    shared = {
        "research_data_boundary_bundle": {"bundle_id": "boundary-1"},
        "tool_operation_registry": {"version": "1.0.0"},
        "research_mode_registry": {"version": "1.0.0"},
    }
    assert set(await run_m01({**shared, "quant_method_policy_config": {}, "frequency_annualization_registry": {}}, context)) == {
        "return_risk_volatility_handler_bundle", "return_volatility_method_manifest"
    }
    assert set(await run_m02({**shared, "dependence_method_policy_config": {}, "entropy_discretization_registry": {}}, context)) == {
        "dependence_entropy_handler_bundle", "dependence_entropy_method_manifest"
    }
    assert set(await run_m03({**shared, "event_scenario_method_policy_config": {}}, context)) == {
        "event_window_scenario_handler_bundle", "event_scenario_method_manifest"
    }
