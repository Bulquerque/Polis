from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.resources import s3_registries
from .errors import ObserverContractError, ObserverErrorCode
from .output import build_s3_artifact
from .proposals import budget_decisions

_REQUIRED_INPUTS = (
    "validated_observer_spec_registry",
    "foundational_hypothesis_core_registry",
    "feature_parameter_policy_registry",
    "observer_change_review_registry",
)


def _require_inputs(inputs: Mapping[str, Any]) -> None:
    for name in _REQUIRED_INPUTS:
        if name not in inputs or not isinstance(inputs[name], Mapping):
            raise ObserverContractError(
                ObserverErrorCode.INPUT_MISSING,
                f"{name} required",
                path="inputs",
            )


def _partition_specs(
    specs: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts = Counter(str(item.get("hypothesis_id")) for item in specs)
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for spec in specs:
        hypothesis_id = str(spec.get("hypothesis_id"))
        if counts[hypothesis_id] > limit:
            reason = "PARAMETER_BUDGET_EXCEEDED"
        elif spec.get("status") != "ACTIVE":
            reason = "OBSERVER_INACTIVE"
        else:
            approved.append(spec)
            continue
        rejected.append(
            {
                "observer_id": spec["observer_id"],
                "hypothesis_id": hypothesis_id,
                "reason": reason,
            }
        )
    return approved, rejected


def _approved_interactions(approved_hypothesis_ids: set[str]) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    registry = s3_registries()["INTERACTION_REGISTRY"]
    for item in registry.get("records", []):
        parents = set(item.get("parent_hypothesis_ids", []))
        if parents and parents.issubset(approved_hypothesis_ids):
            interactions.append(dict(item))
    return interactions


def _budget_records(
    hypotheses: list[dict[str, Any]],
    approved: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    counts = Counter(item["hypothesis_id"] for item in approved)
    return [
        {
            "hypothesis_id": item["hypothesis_id"],
            "approved_count": counts[item["hypothesis_id"]],
            "limit": limit,
            "status": "WITHIN_BUDGET",
        }
        for item in hypotheses
    ]


def apply_budget(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _require_inputs(inputs)
    specs = [
        dict(item)
        for item in inputs["validated_observer_spec_registry"].get("records", [])
    ]
    hypotheses = [
        dict(item)
        for item in inputs["foundational_hypothesis_core_registry"].get(
            "records", []
        )
    ]
    policy = inputs["feature_parameter_policy_registry"].get("records", [{}])[0]
    limit = int(policy.get("max_parameterizations_per_hypothesis", 2))
    approved, rejected = _partition_specs(specs, limit)
    approved_hypothesis_ids = {item["hypothesis_id"] for item in approved}
    approved_hypotheses = [
        item
        for item in hypotheses
        if item["hypothesis_id"] in approved_hypothesis_ids
    ]
    interactions = _approved_interactions(approved_hypothesis_ids)
    budget = _budget_records(hypotheses, approved, limit)

    def build(name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        return build_s3_artifact(
            name=name,
            module_id="P4.S3.M05",
            context=context,
            records=records,
            schema=schemas[name],
        )

    outputs = {
        "approved_hypothesis_passport_registry": build(
            "approved_hypothesis_passport_registry", approved_hypotheses
        ),
        "approved_observer_execution_registry": build(
            "approved_observer_execution_registry", approved
        ),
        "approved_interaction_registry": build(
            "approved_interaction_registry", interactions
        ),
        "hypothesis_budget_report": build("hypothesis_budget_report", budget),
        "rejected_hypothesis_registry": build(
            "rejected_hypothesis_registry", rejected
        ),
    }
    outputs["observer_change_decision_registry"] = budget_decisions(
        inputs["observer_change_review_registry"],
        context,
        schemas["observer_change_decision_registry"],
    )
    return outputs
