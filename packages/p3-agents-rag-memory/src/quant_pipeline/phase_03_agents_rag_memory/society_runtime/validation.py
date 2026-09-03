"""Validation helpers for the consolidated society runtime surface."""
from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from .registry import SOCIETY_MODULES


class SocietyRuntimeValidationError(RuntimeError):
    """Raised when the consolidated society surface is incomplete or inconsistent."""


def validate_society_runtime(package_root: Path) -> dict[str, Any]:
    """Validate module contracts, imports and implementation markers."""
    package_root = package_root.resolve()
    errors: list[str] = []
    module_dir = package_root / "modules"
    for descriptor in SOCIETY_MODULES:
        contract_path = module_dir / (
            descriptor.module_id.replace(".", "_") + "_" + descriptor.module_name + ".yaml"
        )
        if not contract_path.is_file():
            errors.append(f"missing contract: {contract_path.name}")
            continue
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        if not isinstance(contract, Mapping) or contract.get("module_id") != descriptor.module_id:
            errors.append(f"invalid module contract: {contract_path.name}")
        module = import_module(descriptor.import_path)
        if not bool(getattr(module, "IMPLEMENTED", False)):
            errors.append(f"module not marked implemented: {descriptor.module_id}")
        if not callable(getattr(module, "run_module", None)):
            errors.append(f"run_module missing: {descriptor.module_id}")
    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "module_count": len(SOCIETY_MODULES),
        "production_promotion_allowed": False,
    }


def require_valid_society_runtime(package_root: Path) -> None:
    """Fail closed when the consolidated society surface is not valid."""
    result = validate_society_runtime(package_root)
    if result["status"] != "PASS":
        raise SocietyRuntimeValidationError(str(result["errors"]))
