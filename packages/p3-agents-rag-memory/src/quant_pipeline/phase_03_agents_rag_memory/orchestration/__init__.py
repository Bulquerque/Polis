"""Integrated P3 assembly, execution and boundary surfaces."""

from .assembly import (
    artifact_pointer,
    build_foundation_resource_manifest,
    build_foundation_runtime_manifest,
    identity_from_snapshot,
)
from .boundary import (
    FoundationBundle,
    adapt_runtime_result,
    build_foundation_bundle,
    runtime_manifest_pointer,
    to_runtime_request,
)
from .handoff import FoundationHandoffPublisher, FoundationViews
from .registry import EXECUTABLE_MODULE_REGISTRY, MODULE_REGISTRY, ModuleRegistration, by_id
from .runtime import execute_module, execute_module_async

__all__ = [
    "FoundationBundle",
    "FoundationHandoffPublisher",
    "FoundationViews",
    "EXECUTABLE_MODULE_REGISTRY",
    "MODULE_REGISTRY",
    "ModuleRegistration",
    "adapt_runtime_result",
    "artifact_pointer",
    "build_foundation_bundle",
    "build_foundation_resource_manifest",
    "build_foundation_runtime_manifest",
    "by_id",
    "execute_module",
    "execute_module_async",
    "identity_from_snapshot",
    "runtime_manifest_pointer",
    "to_runtime_request",
    "PublicCycleKernel",
    "LocalP3Resources",
    "build_local_p3_s13_runtime",
]

from .public_kernel import PublicCycleKernel


def __getattr__(name: str):
    if name in {"LocalP3Resources", "build_local_p3_s13_runtime"}:
        from .local_profile import LocalP3Resources, build_local_p3_s13_runtime

        return {
            "LocalP3Resources": LocalP3Resources,
            "build_local_p3_s13_runtime": build_local_p3_s13_runtime,
        }[name]
    raise AttributeError(name)
