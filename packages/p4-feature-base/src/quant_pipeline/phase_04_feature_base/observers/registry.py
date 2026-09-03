from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.resources import s3_registries
from .errors import ObserverContractError, ObserverErrorCode
from .output import build_s3_artifact
from .proposals import review_proposals


def _records(value: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    records = value.get("records")
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        raise ObserverContractError(
            ObserverErrorCode.REGISTRY_INVALID,
            "records must be objects",
            path=name,
        )
    return [dict(item) for item in records]


def _assert_unique(
    records: list[dict[str, Any]],
    field: str,
    registry_name: str,
) -> None:
    values = [str(item.get(field, "")) for item in records]
    if any(not value for value in values) or len(values) != len(set(values)):
        raise ObserverContractError(
            ObserverErrorCode.REGISTRY_INVALID,
            f"invalid or duplicate {field}",
            path=registry_name,
        )


def _validate_references(
    families: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    specs: list[dict[str, Any]],
) -> None:
    family_ids = {item["family_id"] for item in families}
    hypothesis_ids = {item["hypothesis_id"] for item in hypotheses}
    for item in hypotheses:
        if item.get("family_id") not in family_ids:
            raise ObserverContractError(
                ObserverErrorCode.REGISTRY_INVALID,
                "unknown family",
                path=str(item.get("hypothesis_id")),
            )
    for item in specs:
        if item.get("hypothesis_id") not in hypothesis_ids:
            raise ObserverContractError(
                ObserverErrorCode.REGISTRY_INVALID,
                "unknown hypothesis",
                path=str(item.get("observer_id")),
            )


def build_registry_artifacts(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    registries = s3_registries()
    families = _records(registries["FEATURE_FAMILY_REGISTRY"], "families")
    hypotheses = _records(
        registries["FOUNDATIONAL_HYPOTHESIS_CORE"],
        "hypotheses",
    )
    specs = _records(registries["OBSERVER_SPEC_REGISTRY"], "specs")
    _assert_unique(families, "family_id", "families")
    _assert_unique(hypotheses, "hypothesis_id", "hypotheses")
    _assert_unique(specs, "observer_id", "specs")
    _validate_references(families, hypotheses, specs)
    outputs = {
        "feature_observer_registry": build_s3_artifact(
            name="feature_observer_registry",
            module_id="P4.S3.M01",
            context=context,
            records=specs,
            schema=schemas["feature_observer_registry"],
        ),
        "feature_parameter_policy_registry": build_s3_artifact(
            name="feature_parameter_policy_registry",
            module_id="P4.S3.M01",
            context=context,
            records=[dict(registries["FEATURE_PARAMETER_POLICY"])],
            schema=schemas["feature_parameter_policy_registry"],
        ),
        "foundational_hypothesis_core_registry": build_s3_artifact(
            name="foundational_hypothesis_core_registry",
            module_id="P4.S3.M01",
            context=context,
            records=hypotheses,
            schema=schemas["foundational_hypothesis_core_registry"],
            extra={"family_count": len(families)},
        ),
    }
    outputs["observer_change_review_registry"] = review_proposals(
        inputs.get("observer_change_proposal_registry"),
        context,
        schemas["observer_change_review_registry"],
    )
    return outputs
