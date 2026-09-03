"""Explicit, immutable module registry."""
from __future__ import annotations

from .domain.core import ModuleDescriptor
from .registry_data import MODULE_ROWS

MODULES: dict[str, ModuleDescriptor] = {
    row[0]: ModuleDescriptor(
        module_id=row[0],
        name=row[1],
        subphase_id=".".join(row[0].split(".")[:2]),
        required_inputs=row[2],
        optional_inputs=row[3],
        outputs=row[4],
        allowed_actions=row[5],
        allowed_modes=row[6],
        capability=row[7],
    )
    for row in MODULE_ROWS
}


def get_module(module_id: str) -> ModuleDescriptor:
    try:
        return MODULES[module_id]
    except KeyError as exc:
        raise KeyError(f"unknown P5 module: {module_id}") from exc


def list_modules() -> tuple[ModuleDescriptor, ...]:
    return tuple(MODULES[key] for key in sorted(MODULES))
