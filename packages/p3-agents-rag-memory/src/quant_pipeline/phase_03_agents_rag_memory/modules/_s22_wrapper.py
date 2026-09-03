from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..runtime_shared.s22_errors import S22InputError
from ..runtime_shared.s22_hashing import canonical_json
from ..runtime_shared.s22_models import BeliefPolicyConfig

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_model(
    inputs: Mapping[str, object],
    key: str,
    model_type: type[ModelT],
    *,
    module_id: str,
) -> ModelT:
    if key not in inputs:
        raise S22InputError(
            code="INPUT_MISSING",
            message=f"required input is missing: {key}",
            module_id=module_id,
        )
    value = inputs[key]
    if isinstance(value, model_type):
        return value
    try:
        return model_type.model_validate_json(canonical_json(value))
    except ValidationError as exc:
        raise S22InputError(
            code="INPUT_INVALID",
            message=f"input failed validation: {key}",
            module_id=module_id,
            details={"errors": exc.errors(include_input=False)},
        ) from exc


def parse_policy(config: Mapping[str, object] | None, *, module_id: str) -> BeliefPolicyConfig:
    if not config or "belief_policy" not in config:
        return BeliefPolicyConfig()
    value = config["belief_policy"]
    if isinstance(value, BeliefPolicyConfig):
        return value
    try:
        return BeliefPolicyConfig.model_validate_json(canonical_json(value))
    except ValidationError as exc:
        raise S22InputError(
            code="CONFIG_INVALID",
            message="belief_policy failed validation",
            module_id=module_id,
            details={"errors": exc.errors(include_input=False)},
        ) from exc
