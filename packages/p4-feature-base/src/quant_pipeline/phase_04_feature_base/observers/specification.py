from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..errors import BoundaryContractError
from ..runtime.forbidden import scan_fields
from ..runtime.schema_validation import validate_json_schema
from .errors import ObserverContractError, ObserverErrorCode
from .output import build_s3_artifact

ALLOWED_OPERATORS = frozenset(
    {
        "identity",
        "lag",
        "difference",
        "return",
        "rolling_mean",
        "rolling_std",
        "ewma",
        "zscore",
        "slope",
        "drawdown",
        "rank",
        "beta",
        "correlation",
        "residual",
        "spread",
        "market_mode_share",
        "connectedness_proxy",
    }
)
RELATIONAL_OPERATORS = frozenset(
    {
        "beta",
        "correlation",
        "residual",
        "spread",
        "market_mode_share",
        "connectedness_proxy",
    }
)
_REQUIRED_FIELDS = (
    "observer_id",
    "hypothesis_id",
    "family_id",
    "operator",
    "input_variables",
    "parameters",
    "parameter_role",
    "engine",
)


def _validate_parameters(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return ["parameters must be mapping"]
    errors: list[str] = []
    for key in ("window", "periods"):
        if key in value and (
            not isinstance(value[key], int) or int(value[key]) < 1
        ):
            errors.append(f"{key} invalid")
    return errors


def _validate_spec(
    spec: Mapping[str, Any],
    hypothesis_ids: set[str],
) -> list[str]:
    errors = [f"missing {field}" for field in _REQUIRED_FIELDS if field not in spec]
    operator = str(spec.get("operator"))
    if str(spec.get("hypothesis_id")) not in hypothesis_ids:
        errors.append("unknown hypothesis")
    if operator not in ALLOWED_OPERATORS:
        errors.append("unsupported operator")
    inputs = spec.get("input_variables")
    if not isinstance(inputs, list) or not inputs or not all(
        isinstance(item, str) and item for item in inputs
    ):
        errors.append("input_variables invalid")
    if spec.get("parameter_role") not in {"PRIMARY", "ROBUSTNESS"}:
        errors.append("parameter_role invalid")
    expected_engine = "RELATIONAL" if operator in RELATIONAL_OPERATORS else "CAUSAL"
    if spec.get("engine") != expected_engine:
        errors.append(f"engine must be {expected_engine}")
    try:
        scan_fields(spec)
    except BoundaryContractError:
        errors.append("forbidden predictive field")
    errors.extend(_validate_parameters(spec.get("parameters", {})))
    return errors


def _validate_inputs(
    inputs: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in (
        "feature_observer_registry",
        "foundational_hypothesis_core_registry",
    ):
        if name not in inputs or not isinstance(inputs[name], Mapping):
            raise ObserverContractError(
                ObserverErrorCode.INPUT_MISSING,
                f"{name} required",
                path="inputs",
            )
        validate_json_schema(inputs[name], schemas[name], name)


def validate_specs(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _validate_inputs(inputs, schemas)
    specs = inputs["feature_observer_registry"].get("records", [])
    hypothesis_ids = {
        item["hypothesis_id"]
        for item in inputs["foundational_hypothesis_core_registry"].get(
            "records", []
        )
    }
    valid: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for spec in specs:
        issues = _validate_spec(spec, hypothesis_ids)
        report.append(
            {
                "observer_id": str(spec.get("observer_id", "")),
                "status": "REJECTED" if issues else "VALIDATED",
                "issues": issues,
            }
        )
        if not issues:
            valid.append(dict(spec))
    return {
        "validated_observer_spec_registry": build_s3_artifact(
            name="validated_observer_spec_registry",
            module_id="P4.S3.M02",
            context=context,
            records=valid,
            schema=schemas["validated_observer_spec_registry"],
        ),
        "observer_spec_validation_report": build_s3_artifact(
            name="observer_spec_validation_report",
            module_id="P4.S3.M02",
            context=context,
            records=report,
            schema=schemas["observer_spec_validation_report"],
        ),
    }
