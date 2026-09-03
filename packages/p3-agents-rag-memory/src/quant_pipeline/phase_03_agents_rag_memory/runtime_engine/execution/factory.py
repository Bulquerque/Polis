from __future__ import annotations

from dataclasses import dataclass

from ..registry import EXECUTION_SLICES
from .capability import ClosurePipelineCapability, ModulePipelineCapability, ProductPipelineCapability
from .ports import JsonArtifactRepositoryPort, ModuleBindingPort, ModuleExecutorPort


@dataclass(frozen=True, slots=True)
class ProductionCapabilities:
    context_capability: ModulePipelineCapability
    cognition_capability: ModulePipelineCapability
    closure_capability: ClosurePipelineCapability
    analytics_capability: ModulePipelineCapability
    products_capability: ProductPipelineCapability


def build_production_capabilities(
    *,
    binding: ModuleBindingPort,
    executor: ModuleExecutorPort,
    repository: JsonArtifactRepositoryPort,
) -> ProductionCapabilities:
    return ProductionCapabilities(
        context_capability=ModulePipelineCapability("CONTEXT", EXECUTION_SLICES["CONTEXT"], binding, executor, repository),
        cognition_capability=ModulePipelineCapability("COGNITION", EXECUTION_SLICES["COGNITION"], binding, executor, repository),
        closure_capability=ClosurePipelineCapability(
            "SOCIETY_CLOSURE", EXECUTION_SLICES["SOCIETY_CLOSURE"], binding, executor, repository
        ),
        analytics_capability=ModulePipelineCapability(
            "SOCIETY_ANALYTICS", EXECUTION_SLICES["SOCIETY_ANALYTICS"], binding, executor, repository
        ),
        products_capability=ProductPipelineCapability("PRODUCTS", EXECUTION_SLICES["PRODUCTS"], binding, executor, repository),
    )
