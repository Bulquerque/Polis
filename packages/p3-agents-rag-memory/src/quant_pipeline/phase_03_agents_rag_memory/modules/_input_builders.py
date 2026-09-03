"""Typed request builders that keep orchestration-only metadata out of domain contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def model_from_declared_inputs(
    model_type: type[ModelT],
    inputs: Mapping[str, Any],
    *,
    aliases: Mapping[str, str] | None = None,
    injected: Mapping[str, Any] | None = None,
) -> ModelT:
    """Construct a strict request from the module's declared artifact inputs.

    ``request`` remains accepted only as a compatibility input for existing
    callers. New orchestration must pass the fields declared in the module
    contract, which makes interface drift detectable by tests.
    """

    existing = inputs.get("request")
    if isinstance(existing, model_type):
        return existing
    if existing is not None:
        return model_type.model_validate(existing, strict=True)

    aliases = dict(aliases or {})
    injected = dict(injected or {})
    payload: dict[str, Any] = {}
    missing: list[str] = []
    for field_name in model_type.model_fields:
        if field_name in injected:
            payload[field_name] = injected[field_name]
            continue
        source_name = aliases.get(field_name, field_name)
        if source_name in inputs:
            payload[field_name] = inputs[source_name]
            continue
        field = model_type.model_fields[field_name]
        if field.is_required():
            missing.append(source_name)
    if missing:
        raise KeyError(
            f"missing declared inputs for {model_type.__name__}: {sorted(set(missing))}"
        )
    return model_type.model_validate(payload, strict=True)
