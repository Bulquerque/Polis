"""Structural and executable-contract validators for the integrated P3 package."""
from __future__ import annotations

import importlib
from pathlib import Path

from .module_contracts import ModuleContractError, validate_declared_module_metadata
from .registry import (
    EXECUTABLE_MODULE_REGISTRY,
    LEGACY_MODULE_REGISTRY,
    RESEARCH_TOOLS_EXTENSION_MODULE_REGISTRY,
)

DEPRECATED_NAMESPACES = (
    "p3_a4_resources",
    "p3_s12_document_rag",
    "p3_s13_temporal_graphrag",
    "p3_s15_tool_registry",
    "p3_s16_gateway",
)


def validate_registry() -> list[str]:
    errors: list[str] = []
    module_ids = [registration.module_id for registration in EXECUTABLE_MODULE_REGISTRY]
    if len(module_ids) != 128 or len(set(module_ids)) != 128:
        errors.append(f"expected 128 unique executable modules, found {len(module_ids)}/{len(set(module_ids))}")
    if len(LEGACY_MODULE_REGISTRY) != 81:
        errors.append(f"legacy P3 authority must preserve 81 modules, found {len(LEGACY_MODULE_REGISTRY)}")
    if len(RESEARCH_TOOLS_EXTENSION_MODULE_REGISTRY) != 47:
        errors.append(
            "research-tools extension authority must contain 47 modules, "
            f"found {len(RESEARCH_TOOLS_EXTENSION_MODULE_REGISTRY)}"
        )
    for registration in EXECUTABLE_MODULE_REGISTRY:
        try:
            module = importlib.import_module(registration.implementation_path)
        except Exception as exc:
            errors.append(f"{registration.module_id} import failed: {exc}")
            continue
        if getattr(module, "MODULE_ID", None) != registration.module_id:
            errors.append(f"{registration.module_id} wrapper identity mismatch")
        try:
            validate_declared_module_metadata(registration.module_id, module)
        except ModuleContractError as exc:
            errors.append(str(exc))
    return errors


def validate_source_tree(source_root: Path) -> list[str]:
    errors: list[str] = []
    for path in source_root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("from ", "import ")):
                continue
            for namespace in DEPRECATED_NAMESPACES:
                if namespace in stripped:
                    errors.append(f"deprecated namespace import {namespace} in {path}")
    return errors
