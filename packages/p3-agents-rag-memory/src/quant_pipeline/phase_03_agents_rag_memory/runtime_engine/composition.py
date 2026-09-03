from __future__ import annotations

from dataclasses import dataclass

from .dependency_check import DependencyCapability, dependency_capabilities, missing_core_dependencies
from .errors import BoundaryValidationError
from .execution import (
    JsonArtifactRepositoryPort,
    ModuleBindingPort,
    ModuleExecutorPort,
    build_production_capabilities,
)
from .foundation_consumer import FoundationManifestConsumer
from .kernel import CycleKernel
from .ports import ArtifactResolverPort, CycleCapabilityPort


@dataclass(frozen=True, slots=True)
class RuntimeComposition:
    """Active runtime composition surface."""

    dependencies: tuple[DependencyCapability, ...]
    foundation_consumer: FoundationManifestConsumer | None = None
    cycle_kernel: CycleKernel | None = None
    production_promotion_allowed: bool = False


def build_runtime_composition(
    *,
    artifact_resolver: ArtifactResolverPort | None = None,
    context_capability: CycleCapabilityPort | None = None,
    cognition_capability: CycleCapabilityPort | None = None,
    closure_capability: CycleCapabilityPort | None = None,
    analytics_capability: CycleCapabilityPort | None = None,
    products_capability: CycleCapabilityPort | None = None,
    module_binding: ModuleBindingPort | None = None,
    module_executor: ModuleExecutorPort | None = None,
    artifact_repository: JsonArtifactRepositoryPort | None = None,
) -> RuntimeComposition:
    """Build the contract-only surface or a complete runtime Cycle Kernel."""

    _require_core_dependencies()
    production_capabilities = all(
        item is not None for item in (module_binding, module_executor, artifact_repository)
    )
    capabilities = _resolve_capabilities(
        context_capability=context_capability,
        cognition_capability=cognition_capability,
        closure_capability=closure_capability,
        analytics_capability=analytics_capability,
        products_capability=products_capability,
        module_binding=module_binding,
        module_executor=module_executor,
        artifact_repository=artifact_repository,
    )
    _validate_capability_graph(artifact_resolver, *capabilities)
    consumer, kernel = _build_kernel(
        artifact_resolver,
        *capabilities,
        require_complete_trace=production_capabilities,
    )
    return RuntimeComposition(
        dependencies=dependency_capabilities(),
        foundation_consumer=consumer,
        cycle_kernel=kernel,
    )


def _require_core_dependencies() -> None:
    missing = missing_core_dependencies()
    if missing:
        raise BoundaryValidationError(f"missing core dependencies: {missing}")


def _resolve_capabilities(
    *,
    context_capability: CycleCapabilityPort | None,
    cognition_capability: CycleCapabilityPort | None,
    closure_capability: CycleCapabilityPort | None,
    analytics_capability: CycleCapabilityPort | None,
    products_capability: CycleCapabilityPort | None,
    module_binding: ModuleBindingPort | None,
    module_executor: ModuleExecutorPort | None,
    artifact_repository: JsonArtifactRepositoryPort | None,
) -> tuple[
    CycleCapabilityPort | None,
    CycleCapabilityPort | None,
    CycleCapabilityPort | None,
    CycleCapabilityPort | None,
    CycleCapabilityPort | None,
]:
    production_parts = (module_binding, module_executor, artifact_repository)
    if any(item is not None for item in production_parts) and not all(
        item is not None for item in production_parts
    ):
        raise BoundaryValidationError(
            "module_binding, module_executor and artifact_repository must be supplied together"
        )
    if not all(item is not None for item in production_parts):
        return context_capability, cognition_capability, closure_capability, analytics_capability, products_capability
    if any(item is not None for item in (context_capability, cognition_capability, closure_capability, analytics_capability, products_capability)):
        raise BoundaryValidationError(
            "explicit capabilities cannot be mixed with production capability factory inputs"
        )
    built = build_production_capabilities(
        binding=module_binding,
        executor=module_executor,
        repository=artifact_repository,
    )
    return built.context_capability, built.cognition_capability, built.closure_capability, built.analytics_capability, built.products_capability


def _validate_capability_graph(
    artifact_resolver: ArtifactResolverPort | None,
    context_capability: CycleCapabilityPort | None,
    cognition_capability: CycleCapabilityPort | None,
    closure_capability: CycleCapabilityPort | None,
    analytics_capability: CycleCapabilityPort | None,
    products_capability: CycleCapabilityPort | None,
) -> None:
    mandatory = (artifact_resolver, context_capability, cognition_capability, closure_capability)
    if any(item is not None for item in mandatory) and not all(item is not None for item in mandatory):
        raise BoundaryValidationError(
            "artifact_resolver, context, cognition and society-closure capabilities must be supplied together"
        )
    if all(item is None for item in mandatory) and any(item is not None for item in (analytics_capability, products_capability)):
        raise BoundaryValidationError("optional capabilities require the mandatory kernel capabilities")
    if products_capability is not None and analytics_capability is None:
        raise BoundaryValidationError("products capability requires society analytics capability")


def _build_kernel(
    artifact_resolver: ArtifactResolverPort | None,
    context_capability: CycleCapabilityPort | None,
    cognition_capability: CycleCapabilityPort | None,
    closure_capability: CycleCapabilityPort | None,
    analytics_capability: CycleCapabilityPort | None,
    products_capability: CycleCapabilityPort | None,
    *,
    require_complete_trace: bool,
) -> tuple[FoundationManifestConsumer | None, CycleKernel | None]:
    if artifact_resolver is None or context_capability is None or cognition_capability is None or closure_capability is None:
        return None, None
    consumer = FoundationManifestConsumer(artifact_resolver)
    return consumer, CycleKernel(
        foundation_resolver=consumer,
        context_capability=context_capability,
        cognition_capability=cognition_capability,
        closure_capability=closure_capability,
        analytics_capability=analytics_capability,
        products_capability=products_capability,
        require_complete_trace=require_complete_trace,
    )
