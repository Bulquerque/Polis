"""Integrated Phase 3: governed foundation, society runtime and external products."""

from .contracts import CONTRACT_PACK_ID, CONTRACT_PACK_VERSION
from .orchestration import (
    MODULE_REGISTRY,
    FoundationBundle,
    adapt_runtime_result,
    build_foundation_bundle,
    execute_module,
    execute_module_async,
    to_runtime_request,
)

__all__ = [
    "CONTRACT_PACK_ID",
    "CONTRACT_PACK_VERSION",
    "FoundationBundle",
    "MODULE_REGISTRY",
    "adapt_runtime_result",
    "build_foundation_bundle",
    "execute_module",
    "execute_module_async",
    "to_runtime_request",
]
