from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.schema_validation import validate_json_schema
from .errors import ObserverContractError, ObserverErrorCode
from .operators.relational import execute_relational
from .operators.temporal import execute_causal
from .output import build_s3_artifact


def _validated_inputs(
    inputs: Mapping[str, Any], schemas: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for name in ("canonical_observation_panel", "approved_observer_execution_registry"):
        if name not in inputs or not isinstance(inputs[name], Mapping):
            raise ObserverContractError(
                ObserverErrorCode.INPUT_MISSING, f"{name} required", path="inputs"
            )
        validate_json_schema(inputs[name], schemas[name], name)
    records = [dict(item) for item in inputs["canonical_observation_panel"].get("records", [])]
    specs = [dict(item) for item in inputs["approved_observer_execution_registry"].get("records", [])]
    return records, specs


def _execution_plan(
    specs: list[dict[str, Any]], records: list[dict[str, Any]], engine: str
) -> list[dict[str, Any]]:
    variable_ids = {str(item.get("variable_id")) for item in records}
    plan: list[dict[str, Any]] = []
    for spec in specs:
        if str(spec.get("engine")) != engine:
            continue
        required = [str(item) for item in spec.get("input_variables", [])]
        missing = sorted(set(required) - variable_ids)
        plan.append(
            {
                "observer_id": str(spec.get("observer_id")),
                "hypothesis_id": str(spec.get("hypothesis_id")),
                "family_id": str(spec.get("family_id")),
                "operator": str(spec.get("operator")),
                "input_variables": required,
                "parameters": dict(spec.get("parameters", {})),
                "engine": engine,
                "execution_stage": "P4.S4_ATOMIC_FACTORIES",
                "materialize_in_s3": False,
                "coverage_status": "READY" if not missing else "DEGRADED_INPUTS_MISSING",
                "missing_input_variables": missing,
            }
        )
    return plan


def _empty_legacy(
    *, name: str, module_id: str, context: ExecutionContext, schema: Mapping[str, Any]
) -> dict[str, Any]:
    return build_s3_artifact(
        name=name,
        module_id=module_id,
        context=context,
        records=[],
        schema=schema,
        extra={
            "execution_status": "SKIPPED_STANDARD_BUILD",
            "reason_code": "MATERIALIZATION_MOVED_TO_S4_TO_AVOID_DUPLICATE_CALCULATION",
        },
    )


def run_causal(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
    materialize: bool = False,
) -> dict[str, Any]:
    records, specs = _validated_inputs(inputs, schemas)
    plan = _execution_plan(specs, records, "CAUSAL")
    outputs = {
        "causal_operator_execution_plan": build_s3_artifact(
            name="causal_operator_execution_plan",
            module_id="P4.S3.M03",
            context=context,
            records=plan,
            schema=schemas["causal_operator_execution_plan"],
        )
    }
    if materialize:
        features, states = execute_causal(specs, records)
        outputs["causal_operator_result_panel"] = build_s3_artifact(
            name="causal_operator_result_panel",
            module_id="P4.S3.M03",
            context=context,
            records=features,
            schema=schemas["causal_operator_result_panel"],
            extra={"execution_status": "DIAGNOSTIC_MATERIALIZATION"},
        )
        outputs["operator_fit_state_registry"] = build_s3_artifact(
            name="operator_fit_state_registry",
            module_id="P4.S3.M03",
            context=context,
            records=states,
            schema=schemas["operator_fit_state_registry"],
            extra={"execution_status": "DIAGNOSTIC_MATERIALIZATION"},
        )
    else:
        outputs["causal_operator_result_panel"] = _empty_legacy(
            name="causal_operator_result_panel",
            module_id="P4.S3.M03",
            context=context,
            schema=schemas["causal_operator_result_panel"],
        )
        outputs["operator_fit_state_registry"] = _empty_legacy(
            name="operator_fit_state_registry",
            module_id="P4.S3.M03",
            context=context,
            schema=schemas["operator_fit_state_registry"],
        )
    return outputs


def run_relational(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
    materialize: bool = False,
) -> dict[str, Any]:
    records, specs = _validated_inputs(inputs, schemas)
    plan = _execution_plan(specs, records, "RELATIONAL")
    outputs = {
        "relational_operator_execution_plan": build_s3_artifact(
            name="relational_operator_execution_plan",
            module_id="P4.S3.M04",
            context=context,
            records=plan,
            schema=schemas["relational_operator_execution_plan"],
        )
    }
    if materialize:
        features, states = execute_relational(specs, records)
        outputs["relational_operator_result_panel"] = build_s3_artifact(
            name="relational_operator_result_panel",
            module_id="P4.S3.M04",
            context=context,
            records=features,
            schema=schemas["relational_operator_result_panel"],
            extra={"execution_status": "DIAGNOSTIC_MATERIALIZATION"},
        )
        outputs["relational_fit_state_registry"] = build_s3_artifact(
            name="relational_fit_state_registry",
            module_id="P4.S3.M04",
            context=context,
            records=states,
            schema=schemas["relational_fit_state_registry"],
            extra={"execution_status": "DIAGNOSTIC_MATERIALIZATION"},
        )
    else:
        outputs["relational_operator_result_panel"] = _empty_legacy(
            name="relational_operator_result_panel",
            module_id="P4.S3.M04",
            context=context,
            schema=schemas["relational_operator_result_panel"],
        )
        outputs["relational_fit_state_registry"] = _empty_legacy(
            name="relational_fit_state_registry",
            module_id="P4.S3.M04",
            context=context,
            schema=schemas["relational_fit_state_registry"],
        )
    return outputs
