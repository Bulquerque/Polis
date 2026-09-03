"""Production execution machinery for the 48 real runtime modules."""

from .bindings import ConventionModuleBindings, MappingRuntimeConfig, RuntimeDependencyRegistry
from .capability import ClosurePipelineCapability, ModulePipelineCapability, ProductPipelineCapability
from .factory import ProductionCapabilities, build_production_capabilities
from .models import ArtifactWriteRequest, ModuleExecutionResult, ModuleInvocation
from .module_executor import PythonModuleExecutor
from .ports import JsonArtifactRepositoryPort, ModuleBindingPort, ModuleExecutorPort, RuntimeConfigPort
from .storage import FileJsonArtifactRepository, InMemoryJsonArtifactRepository

__all__ = [
    "ArtifactWriteRequest",
    "ClosurePipelineCapability",
    "ConventionModuleBindings",
    "FileJsonArtifactRepository",
    "InMemoryJsonArtifactRepository",
    "JsonArtifactRepositoryPort",
    "MappingRuntimeConfig",
    "ModuleBindingPort",
    "ModuleExecutionResult",
    "ModuleExecutorPort",
    "ModuleInvocation",
    "ModulePipelineCapability",
    "ProductPipelineCapability",
    "ProductionCapabilities",
    "PythonModuleExecutor",
    "RuntimeConfigPort",
    "RuntimeDependencyRegistry",
    "build_production_capabilities",
]
