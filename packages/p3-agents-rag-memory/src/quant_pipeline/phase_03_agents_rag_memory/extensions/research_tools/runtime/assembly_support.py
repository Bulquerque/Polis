"""Shared parsing, lineage and operation assembly helpers for P3.S40."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .models import AliasBinding, S40Lineage
from .registry import ExecutableOperation, OperationRegistry

ModelT = TypeVar("ModelT", bound=BaseModel)


def jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def parse(model: type[ModelT], value: object) -> ModelT:
    if isinstance(value, model):
        return value
    return model.model_validate_json(json.dumps(jsonable(value), sort_keys=True))


def lineage(module_id: str, inputs: Mapping[str, Any], names: Iterable[str]) -> S40Lineage:
    source_hashes = {name: content_hash(jsonable(inputs[name])) for name in names if name in inputs}
    return S40Lineage(
        lineage_id=f"{module_id}:{content_hash(source_hashes)[:20]}",
        producer_module_id=module_id,
        source_artifact_ids=tuple(source_hashes),
        source_hashes=source_hashes,
        transformation_ids=(f"{module_id}.v2",),
    )


def operations(
    context: ModuleExecutionContext,
    inputs: Mapping[str, Any],
    *,
    services: Mapping[str, Any] | None = None,
    allow_explicit: bool | None = None,
) -> tuple[ExecutableOperation, ...]:
    """Build one operation set from six declared family surfaces.

    The release path is deterministic and assembled only from declared inputs.
    Explicit process-local operations are retained solely for focused TEST
    fixtures and must be opted into by configuration.
    """
    effective_services = services if services is not None else context.services
    if allow_explicit is None:
        allow_explicit = bool(context.config.get("allow_explicit_research_tool_operations", False))
    if allow_explicit and context.profile.value != "TEST":
        raise RuntimeError("explicit research_tool_operations are TEST-only")

    explicit: tuple[ExecutableOperation, ...] = ()
    if allow_explicit:
        raw = effective_services.get("research_tool_operations", ())
        if not isinstance(raw, (tuple, list)):
            raise TypeError("research_tool_operations service must be a sequence")
        explicit = tuple(raw)
        if any(not isinstance(item, ExecutableOperation) for item in explicit):
            raise TypeError("research_tool_operations contains an invalid item")

    from .company_adapter import build_canonical_company_operations
    from .corpus_adapter import build_corpus_operations
    from .macro_adapter import build_macro_operations
    from .market_adapter import build_market_operations
    from .options_adapter import build_options_operations
    from .quant_adapter import build_canonical_quant_operations

    auto: list[ExecutableOperation] = []
    auto.extend(build_corpus_operations(inputs=inputs, services=effective_services))
    auto.extend(build_market_operations(inputs=inputs, services=effective_services))
    auto.extend(build_options_operations(inputs=inputs, services=effective_services))
    auto.extend(build_macro_operations(inputs=inputs, services=effective_services))

    company_port = effective_services.get("company_pit_query_port") or effective_services.get("pit_research_query_port")
    if company_port is not None and "company_tool_handler_bundle" in inputs:
        auto.extend(build_canonical_company_operations(inputs=inputs, query_port=company_port))
    quant_port = effective_services.get("quant_pit_query_port") or effective_services.get("pit_research_query_port")
    if quant_port is not None and "quant_tool_handler_bundle" in inputs:
        auto.extend(build_canonical_quant_operations(inputs=inputs, query_port=quant_port))

    merged = {item.key: item for item in auto}
    for item in explicit:
        if item.key in merged:
            raise ValueError(f"explicit test operation collides with canonical operation: {item.key}")
        merged[item.key] = item
    return tuple(merged[key] for key in sorted(merged))


def aliases(inputs: Mapping[str, Any]) -> tuple[AliasBinding, ...]:
    raw = inputs.get("compatibility_alias_registry", ())
    if isinstance(raw, Mapping):
        raw = raw.get("aliases", ())
    inferred_operations = {
        "research.search_filings.v1": "search",
        "quant.realized_volatility.v1": "calculate",
    }
    result: list[AliasBinding] = []
    for item in raw if isinstance(raw, (tuple, list)) else ():
        data = jsonable(item)
        if not isinstance(data, Mapping):
            continue
        payload = {
            "alias_tool_id": data.get("alias_tool_id"),
            "alias_operation_id": data.get("alias_operation_id")
            or inferred_operations.get(str(data.get("alias_tool_id")), str(data.get("target_operation_id", "execute"))),
            "target_tool_id": data.get("target_tool_id"),
            "target_operation_id": data.get("target_operation_id"),
            "fixed_arguments": data.get("fixed_arguments", {}),
            "argument_renames": data.get("argument_renames", {}),
            "deprecated": bool(data.get("deprecated", True)),
            "second_handler_forbidden": bool(data.get("second_handler_forbidden", True)),
        }
        result.append(AliasBinding.model_validate(payload))
    return tuple(result)


def registry(
    context: ModuleExecutionContext,
    inputs: Mapping[str, Any],
    *,
    services: Mapping[str, Any] | None = None,
    allow_explicit: bool | None = None,
) -> OperationRegistry:
    executable = operations(
        context,
        inputs,
        services=services,
        allow_explicit=allow_explicit,
    )
    keys = {item.key for item in executable}
    compatible = tuple(
        item for item in aliases(inputs)
        if (item.target_tool_id, item.target_operation_id) in keys
    )
    return OperationRegistry(executable, compatible)


def expected_keys(inputs: Mapping[str, Any]) -> set[tuple[str, str]] | None:
    raw = inputs.get("canonical_tool_operation_registry")
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        raw = raw.get("operations", raw.get("records", ()))
    result: set[tuple[str, str]] = set()
    for item in raw if isinstance(raw, (tuple, list)) else ():
        data = item.model_dump(mode="json") if isinstance(item, BaseModel) else item
        if not isinstance(data, Mapping):
            continue
        tool, operation = data.get("tool_id"), data.get("operation_id")
        if isinstance(tool, str) and isinstance(operation, str):
            result.add((tool, operation))
    return result


def family_reports(value: object) -> tuple[object, ...]:
    if isinstance(value, Mapping):
        normalized: list[object] = []
        for tool_id, report in value.items():
            data = jsonable(report)
            if isinstance(data, dict):
                records = data.get("records", ())
                data["records"] = [
                    {**record, "family_tool_id": str(tool_id)} if isinstance(record, dict) else record
                    for record in records if isinstance(records, list)
                ]
            normalized.append(data)
        return tuple(normalized)
    return tuple(value) if isinstance(value, (tuple, list)) else ()
