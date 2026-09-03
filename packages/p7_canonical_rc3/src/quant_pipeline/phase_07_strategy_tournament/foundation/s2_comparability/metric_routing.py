"""P7.S2.M03 — explicit metric semantics without normalization or scoring."""

from __future__ import annotations

import math

from pydantic import JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact, verify_artifact_hash
from ..canonical import content_sha256
from ..models import ModuleConfig
from ..reason_codes import ReasonCode
from ..s2_errors import P7S2Error
from .common import first_path, get_path, source_artifact_for_path
from .models import (
    MetricDefinition,
    MetricRouteRecord,
    MetricSemanticsRegistry,
    ObjectiveFamilyRegistry,
)

MODULE_ID = "P7.S2.M03"


def execute(
    eligible_payload: dict[str, JsonValue],
    groups_payload: dict[str, JsonValue],
    metric_registry_payload: dict[str, JsonValue],
    objective_registry_payload: dict[str, JsonValue],
    config_payload: dict[str, JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    before = content_sha256(
        {
            "eligible": eligible_payload,
            "groups": groups_payload,
            "metrics": metric_registry_payload,
            "objectives": objective_registry_payload,
        }
    )
    config, eligible, groups, metrics, objectives = _parse_inputs(
        eligible_payload,
        groups_payload,
        metric_registry_payload,
        objective_registry_payload,
        config_payload,
    )
    routes, unavailable = _route_all(eligible.records, groups.records, metrics, objectives)
    outputs = _build_outputs(config, metrics, objectives, routes, unavailable)
    after = content_sha256(
        {
            "eligible": eligible_payload,
            "groups": groups_payload,
            "metrics": metric_registry_payload,
            "objectives": objective_registry_payload,
        }
    )
    if before != after:
        raise P7S2Error(
            ReasonCode.S2_INPUT_MUTATION_DETECTED,
            "metric routing mutated its inputs",
            MODULE_ID,
        )
    return outputs


def _parse_inputs(eligible_payload, groups_payload, metric_payload, objective_payload, config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        eligible = ArtifactEnvelope.model_validate(eligible_payload)
        groups = ArtifactEnvelope.model_validate(groups_payload)
        metrics = MetricSemanticsRegistry.model_validate(metric_payload)
        objectives = ObjectiveFamilyRegistry.model_validate(objective_payload)
    except ValidationError as exc:
        raise P7S2Error(
            ReasonCode.METRIC_SEMANTICS_UNKNOWN,
            "metric routing inputs or registries failed validation",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    _validate_artifact(eligible, "eligible_strategy_candidate_panel")
    _validate_artifact(groups, "candidate_comparison_group_panel")
    _validate_registry_links(metrics, objectives)
    return config, eligible, groups, metrics, objectives


def _validate_artifact(artifact: ArtifactEnvelope, expected_name: str) -> None:
    if artifact.artifact_name != expected_name or not verify_artifact_hash(artifact):
        raise P7S2Error(
            ReasonCode.S2_INPUT_INVALID,
            f"{expected_name} is invalid or has a mismatched hash",
            MODULE_ID,
        )


def _validate_registry_links(metrics, objectives) -> None:
    metric_ids = set(metrics.mapping())
    missing = sorted(
        {
            metric_id
            for family in objectives.families
            for metric_id in family.required_metric_ids + family.optional_metric_ids
            if metric_id not in metric_ids
        }
    )
    if missing:
        raise P7S2Error(
            ReasonCode.METRIC_SEMANTICS_UNKNOWN,
            "objective registry references unknown metrics",
            MODULE_ID,
            {"metric_ids": missing},
        )


def _route_all(candidate_records, group_records, metrics, objectives):
    candidates = _unique_by_candidate(candidate_records, "eligible candidates")
    groups = _unique_by_candidate(group_records, "comparison groups")
    if set(candidates) != set(groups):
        raise P7S2Error(
            ReasonCode.REQUIRED_METRIC_ROUTE_MISSING,
            "eligible candidate and comparison group sets do not reconcile",
            MODULE_ID,
            {
                "without_group": sorted(set(candidates) - set(groups)),
                "without_candidate": sorted(set(groups) - set(candidates)),
            },
        )
    metric_map = metrics.mapping()
    family_map = objectives.mapping()
    routes: list[dict[str, JsonValue]] = []
    unavailable = 0
    route_ids: set[str] = set()
    for candidate_id in sorted(candidates):
        candidate = candidates[candidate_id]
        group = groups[candidate_id]
        family_id = candidate.get("objective_family")
        family = family_map.get(str(family_id))
        if family is None:
            raise P7S2Error(
                ReasonCode.METRIC_SEMANTICS_UNKNOWN,
                "eligible candidate objective family has no metric contract",
                MODULE_ID,
                {"candidate_id": candidate_id, "objective_family": family_id},
            )
        required = set(family.required_metric_ids)
        ordered_ids = family.required_metric_ids + family.optional_metric_ids
        for metric_id in ordered_ids:
            route = _route_metric(
                candidate,
                str(group["comparison_group_id"]),
                metric_map[metric_id],
                metric_id in required,
            )
            if route["metric_route_id"] in route_ids:
                raise P7S2Error(
                    ReasonCode.METRIC_ROUTE_DUPLICATE,
                    "metric route identity is not unique",
                    MODULE_ID,
                    {"metric_route_id": route["metric_route_id"]},
                )
            route_ids.add(str(route["metric_route_id"]))
            unavailable += route["status"] == "UNAVAILABLE"
            routes.append(route)
    routes.sort(key=lambda item: (str(item["candidate_id"]), str(item["metric_id"])))
    return routes, unavailable


def _unique_by_candidate(records, label):
    result: dict[str, dict[str, JsonValue]] = {}
    for record in records:
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in result:
            raise P7S2Error(
                ReasonCode.METRIC_ROUTE_DUPLICATE,
                f"{label} must contain unique candidate IDs",
                MODULE_ID,
                {"candidate_id": candidate_id},
            )
        result[candidate_id] = record
    return result


def _route_metric(candidate, group_id, definition: MetricDefinition, required: bool):
    resolved = first_path(candidate, definition.source_paths)
    if resolved is None:
        if required or definition.missingness_policy == "BLOCK":
            raise P7S2Error(
                ReasonCode.REQUIRED_METRIC_ROUTE_MISSING,
                "required metric has no available source path",
                MODULE_ID,
                {"candidate_id": candidate.get("candidate_id"), "metric_id": definition.metric_id},
            )
        path = definition.source_paths[0]
        value: JsonValue | None = None
        status = "UNAVAILABLE"
    else:
        path, raw = resolved
        _validate_value(raw, definition, candidate)
        _validate_units(candidate, path, definition)
        value = raw
        status = "AVAILABLE"
    identity = {
        "candidate_id": candidate.get("candidate_id"),
        "comparison_group_id": group_id,
        "metric_id": definition.metric_id,
        "semantic_version": definition.semantic_version,
        "source_path": path,
    }
    return MetricRouteRecord(
        metric_route_id=f"route-{content_sha256(identity)}",
        candidate_id=str(candidate["candidate_id"]),
        comparison_group_id=group_id,
        metric_id=definition.metric_id,
        source_artifact_name=source_artifact_for_path(path),
        source_path=path,
        units=definition.units,
        direction=definition.direction,
        required=required,
        transformation_policy=definition.transformation_policy,
        missingness_policy=definition.missingness_policy,
        semantic_version=definition.semantic_version,
        status=status,
        raw_value=value,
    ).model_dump(mode="json")


def _validate_value(raw, definition, candidate) -> None:
    valid = True
    if definition.value_type == "NUMBER":
        valid = isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(float(raw))
    elif definition.value_type == "INTEGER":
        valid = isinstance(raw, int) and not isinstance(raw, bool)
    elif definition.value_type == "BOOLEAN":
        valid = isinstance(raw, bool)
    elif definition.value_type == "STRING":
        valid = isinstance(raw, str) and bool(raw)
    if not valid:
        raise P7S2Error(
            ReasonCode.REQUIRED_METRIC_UNAVAILABLE,
            "metric source value does not match its declared type",
            MODULE_ID,
            {
                "candidate_id": candidate.get("candidate_id"),
                "metric_id": definition.metric_id,
                "value_type": definition.value_type,
            },
        )


def _validate_units(candidate, path: str, definition: MetricDefinition) -> None:
    parts = path.split(".")
    container_path = ".".join(parts[:-1])
    field = parts[-1]
    container = get_path(candidate, container_path, None) if container_path else candidate
    if not isinstance(container, dict):
        return
    declared = container.get(f"{field}_units")
    if declared is not None and declared != definition.units:
        raise P7S2Error(
            ReasonCode.METRIC_UNIT_INCOMPATIBLE,
            "metric source units conflict with the semantic registry",
            MODULE_ID,
            {
                "candidate_id": candidate.get("candidate_id"),
                "metric_id": definition.metric_id,
                "declared_units": declared,
                "registry_units": definition.units,
            },
        )


def _build_outputs(config, metrics, objectives, routes, unavailable):
    route_artifact = create_artifact(
        artifact_name="candidate_metric_route_panel",
        records=routes,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate_metric",
    )
    audit_artifact = create_artifact(
        artifact_name="metric_route_audit",
        records=[
            {
                "status": "PASS",
                "metric_registry_id": metrics.registry_id,
                "metric_registry_version": metrics.registry_version,
                "objective_registry_id": objectives.registry_id,
                "objective_registry_version": objectives.registry_version,
                "route_count": len(routes),
                "available_route_count": len(routes) - unavailable,
                "unavailable_route_count": unavailable,
            }
        ],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_metric_routing_run",
    )
    return {
        "candidate_metric_route_panel": route_artifact.model_dump(mode="json"),
        "metric_route_audit": audit_artifact.model_dump(mode="json"),
    }
