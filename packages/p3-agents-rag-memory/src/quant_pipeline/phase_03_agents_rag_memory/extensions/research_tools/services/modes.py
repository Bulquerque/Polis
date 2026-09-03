"""P3.S32.M02 implementation."""

from __future__ import annotations

from collections import Counter

from pydantic import ValidationError

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalToolOperationRegistry,
    OperationModeMatrix,
    OperationModeMatrixRecord,
    ResearchModeRegistry,
    ResearchModeSpec,
)
from ..contracts.configs import OperationModeRegistryConfig, ResearchCapabilityTaxonomyConfig
from ..core.errors import fail
from ..core.identifiers import MODE_ID_RE, require_match
from .artifact_construction import finalize, lineage


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _assert_acyclic(edges: dict[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise fail("P3RT-MODE-0002", "downgrade graph contains a cycle", {"mode": node})
        if node in visited:
            return
        visiting.add(node)
        for target in edges.get(node, ()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node)



def _canonical_inputs(
    mode_config: OperationModeRegistryConfig,
    capability_taxonomy: ResearchCapabilityTaxonomyConfig,
) -> tuple[OperationModeRegistryConfig, ResearchCapabilityTaxonomyConfig]:
    templates = tuple(
        template.model_copy(
            update={
                "required_capabilities": tuple(sorted(set(template.required_capabilities))),
                "required_methods": tuple(sorted(set(template.required_methods))),
                "required_view_classes": tuple(sorted(set(template.required_view_classes))),
            }
        )
        for template in sorted(mode_config.templates, key=lambda item: item.mode_id)
    )
    assignments = tuple(
        assignment.model_copy(
            update={
                "mode_ids": tuple(sorted(set(assignment.mode_ids))),
                "downgrade_targets": {
                    mode_id: tuple(sorted(set(targets)))
                    for mode_id, targets in sorted(assignment.downgrade_targets.items())
                },
                "overrides": {
                    mode_id: dict(sorted(values.items()))
                    for mode_id, values in sorted(assignment.overrides.items())
                },
            }
        )
        for assignment in sorted(
            mode_config.assignments, key=lambda item: (item.tool_id, item.operation_id)
        )
    )
    canonical_modes = mode_config.model_copy(
        update={"templates": templates, "assignments": assignments}
    )
    canonical_capabilities = capability_taxonomy.model_copy(
        update={
            "capabilities": tuple(
                sorted(capability_taxonomy.capabilities, key=lambda item: item.capability_id)
            )
        }
    )
    return canonical_modes, canonical_capabilities


def build_modes(
    *,
    operation_registry: CanonicalToolOperationRegistry,
    mode_config: OperationModeRegistryConfig,
    capability_taxonomy: ResearchCapabilityTaxonomyConfig,
) -> tuple[ResearchModeRegistry, OperationModeMatrix]:
    mode_config, capability_taxonomy = _canonical_inputs(mode_config, capability_taxonomy)
    operation_by_key = {
        (item.tool_id, item.operation_id): item for item in operation_registry.operations
    }
    capability_ids = {item.capability_id for item in capability_taxonomy.capabilities}
    template_ids = [item.mode_id for item in mode_config.templates]
    duplicate_templates = _duplicates(template_ids)
    if duplicate_templates:
        raise fail("P3RT-MODE-0006", "duplicate mode templates", {"mode_ids": duplicate_templates})
    templates = {item.mode_id: item for item in mode_config.templates}

    assignment_keys = [f"{item.tool_id}/{item.operation_id}" for item in mode_config.assignments]
    duplicates = _duplicates(assignment_keys)
    if duplicates:
        raise fail("P3RT-MODE-0007", "duplicate operation mode assignments", {"operations": duplicates})

    modes: list[ResearchModeSpec] = []
    matrix: list[OperationModeMatrixRecord] = []
    assigned: set[tuple[str, str]] = set()

    for assignment in sorted(mode_config.assignments, key=lambda item: (item.tool_id, item.operation_id)):
        key = (assignment.tool_id, assignment.operation_id)
        operation = operation_by_key.get(key)
        if operation is None:
            raise fail("P3RT-MODE-0001", "mode assignment targets unknown operation", {"operation": key})
        assigned.add(key)
        if set(assignment.mode_ids) != set(operation.supported_mode_ids):
            raise fail(
                "P3RT-MODE-0008",
                "mode assignment differs from operation supported modes",
                {
                    "operation": key,
                    "operation_modes": operation.supported_mode_ids,
                    "assigned_modes": assignment.mode_ids,
                },
            )

        local: dict[str, ResearchModeSpec] = {}
        for mode_id in assignment.mode_ids:
            try:
                require_match(mode_id, MODE_ID_RE, "mode_id")
            except ValueError as exc:
                raise fail("P3RT-MODE-0009", str(exc), {"operation": key}) from exc
            template = templates.get(mode_id)
            if template is None:
                raise fail("P3RT-MODE-0010", "mode template is missing", {"mode_id": mode_id})
            unknown_capabilities = sorted(
                (set(template.required_capabilities) | set(template.required_methods)) - capability_ids
            )
            if unknown_capabilities:
                raise fail(
                    "P3RT-MODE-0004",
                    "mode references unknown capabilities",
                    {"mode_id": mode_id, "capabilities": unknown_capabilities},
                )
            payload = template.model_dump(mode="python")
            payload.update(assignment.overrides.get(mode_id, {}))
            payload.update(
                {
                    "tool_id": assignment.tool_id,
                    "operation_id": assignment.operation_id,
                    "downgrade_targets": assignment.downgrade_targets.get(mode_id, ()),
                }
            )
            try:
                spec = ResearchModeSpec.model_validate(payload)
            except ValidationError as exc:
                raise fail(
                    "P3RT-MODE-0003",
                    "mode limits or override are invalid",
                    {"operation": key, "mode_id": mode_id, "cause": type(exc).__name__},
                ) from exc
            if not set(spec.required_view_classes).issubset(set(operation.required_view_classes)):
                raise fail(
                    "P3RT-MODE-0011",
                    "mode requires a view not declared by the operation",
                    {"operation": key, "mode_id": mode_id},
                )
            local[mode_id] = spec

        edges: dict[str, tuple[str, ...]] = {}
        for mode_id, spec in local.items():
            for target in spec.downgrade_targets:
                target_spec = local.get(target)
                if target_spec is None:
                    raise fail(
                        "P3RT-MODE-0012",
                        "downgrade target is not available for the operation",
                        {"operation": key, "mode_id": mode_id, "target": target},
                    )
                if target_spec.band >= spec.band:
                    raise fail(
                        "P3RT-MODE-0013",
                        "downgrade target must have a lower band",
                        {"operation": key, "mode_id": mode_id, "target": target},
                    )
            edges[mode_id] = spec.downgrade_targets
        _assert_acyclic(edges)
        modes.extend(local.values())
        ordered = sorted(local.values(), key=lambda item: (item.band, item.mode_id))
        matrix.append(
            OperationModeMatrixRecord(
                tool_id=assignment.tool_id,
                operation_id=assignment.operation_id,
                mode_ids=tuple(item.mode_id for item in ordered),
                minimum_mode_id=ordered[0].mode_id,
                maximum_band=max(item.band for item in ordered),
            )
        )

    missing_assignments = sorted(set(operation_by_key) - assigned)
    if missing_assignments:
        raise fail(
            "P3RT-MODE-0005",
            "one or more operations have no executable mode assignment",
            {"operations": missing_assignments},
        )

    source_inputs = (operation_registry, mode_config, capability_taxonomy)
    registry = finalize(
        ResearchModeRegistry,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M02", operation_registry.contract_version, source_inputs),
            "modes": tuple(sorted(modes, key=lambda item: (item.tool_id, item.operation_id, item.band, item.mode_id))),
            "mode_count": len(modes),
        },
    )
    matrix_artifact = finalize(
        OperationModeMatrix,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M02", operation_registry.contract_version, source_inputs),
            "records": tuple(sorted(matrix, key=lambda item: (item.tool_id, item.operation_id))),
        },
    )
    return registry, matrix_artifact
