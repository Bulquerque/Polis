from __future__ import annotations

from .models import (
    ActiveRetroPolicyPatch,
    PersonSchemaPolicy,
    PersonSeedPanel,
    PersonToolEntitlementPanel,
    ProviderAdapterRegistry,
    ToolEntitlementConfig,
    ToolRegistryArtifact,
    ToolRegistryConfig,
)
from .module_m01 import ToolRegistryBuilder
from .module_m02 import PersonToolEntitlementRouter


class P3S15Runner:
    def __init__(
        self,
        *,
        registry_builder: ToolRegistryBuilder,
        entitlement_router: PersonToolEntitlementRouter,
    ) -> None:
        self._registry_builder = registry_builder
        self._entitlement_router = entitlement_router

    async def run(
        self,
        *,
        registry_config: ToolRegistryConfig,
        provider_registry: ProviderAdapterRegistry,
        person_seed_panel: PersonSeedPanel,
        person_schema_policy: PersonSchemaPolicy,
        entitlement_config: ToolEntitlementConfig,
        active_retro_policy_patch: ActiveRetroPolicyPatch | None = None,
    ) -> tuple[ToolRegistryArtifact, PersonToolEntitlementPanel]:
        registry = await self._registry_builder.run(
            config=registry_config,
            provider_registry=provider_registry,
            active_retro_policy_patch=active_retro_policy_patch,
        )
        entitlements = self._entitlement_router.run(
            tool_registry=registry,
            person_seed_panel=person_seed_panel,
            person_schema_policy=person_schema_policy,
            entitlement_config=entitlement_config,
        )
        return registry, entitlements
