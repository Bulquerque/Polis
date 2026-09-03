from __future__ import annotations

from quant_pipeline.phase_09.contracts.s1 import S1ExecutionOutputs

from .base import StrictModel
from .budget import (
    EarlyStoppingPolicy,
    FidelityLevel,
    ResourceCapacitySnapshot,
    SearchBudgetPolicy,
)
from .configuration import ConfigurationIdentityContext, SeedPolicyReference
from .experiment import (
    ExperimentSpecification,
    MetricRegistrySnapshot,
    PhaseCapabilityRegistry,
    PromotionPolicyReference,
)
from .parameters import DeprecationRegistry, PhaseParameterContractSnapshots
from .search_space import SearchSpaceDeclaration
from .trials import SchedulerPolicy, WorkerCapabilitySnapshot


class S2RunRequest(StrictModel):
    s1_outputs: S1ExecutionOutputs
    specification: ExperimentSpecification
    metric_registry: MetricRegistrySnapshot
    capability_registry: PhaseCapabilityRegistry
    promotion_policy: PromotionPolicyReference
    phase_parameter_contracts: PhaseParameterContractSnapshots
    deprecation_registry: DeprecationRegistry
    search_space_declaration: SearchSpaceDeclaration
    resource_capacity: ResourceCapacitySnapshot
    budget_policy: SearchBudgetPolicy
    fidelity_levels: tuple[FidelityLevel, ...]
    early_stopping_policy: EarlyStoppingPolicy
    identity_context: ConfigurationIdentityContext
    scheduler_policy: SchedulerPolicy
    worker_capabilities: WorkerCapabilitySnapshot
    seed_policy: SeedPolicyReference
