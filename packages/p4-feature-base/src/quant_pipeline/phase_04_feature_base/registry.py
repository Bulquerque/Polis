from __future__ import annotations

from collections.abc import Iterable

from .economic_errors import ContractError
from .economic_models import ObserverExecutionRegistry, ObserverSpec


def specs_for_module(
    registry: ObserverExecutionRegistry,
    module_id: str,
    supported_observer_ids: Iterable[str],
) -> tuple[ObserverSpec, ...]:
    supported = set(supported_observer_ids)
    selected = tuple(row for row in registry.records if row.module_id == module_id and row.enabled)
    unknown = sorted({row.observer_id for row in selected if row.observer_id not in supported})
    if unknown:
        raise ContractError(
            f"{module_id.replace('.', '_')}_UNKNOWN_OBSERVER",
            "approved registry contains unsupported observer IDs",
            details={"observer_ids": unknown},
        )
    return selected
