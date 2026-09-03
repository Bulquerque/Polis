"""Pure compatibility projections between canonical foundation capabilities."""

from .governance_to_population import (
    to_population_person_policy,
    to_population_tag_registry,
)
from .governance_to_resources import (
    build_offline_provider_registry,
    to_knowledge_context,
    to_knowledge_snapshot,
)
from .governance_to_warmup import (
    to_history_snapshot_view,
    to_memory_person_policy_view,
    to_memory_snapshot_view,
    to_warmup_retro_patch,
)
from .population_to_resources import to_entitlement_population_view
from .population_to_warmup import (
    to_replay_graph_view,
    to_replay_person_seed_panel,
    to_schedule_graph_view,
    to_schedule_population_view,
)
from .resources_internal import (
    entitlements_to_gateway,
    provider_registry_to_gateway,
    tool_registry_to_gateway,
)
from .resources_to_warmup import to_warmup_resource_manifest

__all__ = [
    "build_offline_provider_registry",
    "entitlements_to_gateway",
    "provider_registry_to_gateway",
    "to_entitlement_population_view",
    "to_history_snapshot_view",
    "to_knowledge_context",
    "to_knowledge_snapshot",
    "to_memory_person_policy_view",
    "to_memory_snapshot_view",
    "to_population_person_policy",
    "to_population_tag_registry",
    "to_replay_graph_view",
    "to_replay_person_seed_panel",
    "to_schedule_graph_view",
    "to_schedule_population_view",
    "to_warmup_resource_manifest",
    "to_warmup_retro_patch",
    "tool_registry_to_gateway",
]
