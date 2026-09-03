from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import (
    PersonSchemaPolicy,
    PersonSeedPanel,
    ProviderAdapterRegistry,
    ToolEntitlementConfig,
    ToolRegistryConfig,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.module_m01 import ToolRegistryBuilder
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.module_m02 import PersonToolEntitlementRouter
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S15_M01_tool_registry_builder import run_module_async as run_registry
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S15_M02_person_tool_entitlement_router import run_module as run_entitlements


@dataclass
class ListEventSink:
    events: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    def emit(self, event: str, dimensions: dict[str, object]) -> None:
        self.events.append((event, dict(dimensions)))


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def person_seed_panel() -> PersonSeedPanel:
    return PersonSeedPanel.model_validate({
        "records": [{
            "person_id": "person-quant-1",
            "economic_role": "quant_researcher",
            "institution": "fund",
            "resources": ["python_runtime"],
            "capabilities": {"quantitative": 0.9, "tool_use": 0.8},
            "constraints": [],
            "allowed_data_classes": ["market_returns"],
            "schema_version": "1.0.0",
        }],
        "lineage_id": "lineage-person-seed-tools",
    }, strict=False)


async def build_s15_outputs(root: Path):
    sink = ListEventSink()
    registry_config = ToolRegistryConfig.model_validate(load_yaml(root / "config/resources/s15/tool_registry_config.yaml"), strict=False)
    providers = ProviderAdapterRegistry.model_validate(load_yaml(root / "config/resources/s15/provider_adapter_registry.example.yaml"), strict=False)
    registry = (await run_registry({
        "tool_registry_config": registry_config,
        "provider_adapter_registry_config": providers,
        "active_retro_policy_patch": None,
    }, {"service": ToolRegistryBuilder(discovery_adapters={}, event_sink=sink)}))["tool_registry"]
    person_policy = PersonSchemaPolicy.model_validate(load_yaml(root / "config/resources/s15/person_schema_policy.yaml"), strict=False)
    entitlement_config = ToolEntitlementConfig.model_validate(load_yaml(root / "config/resources/s15/tool_entitlement_config.yaml"), strict=False)
    entitlements = run_entitlements({
        "tool_registry": registry,
        "person_seed_panel": person_seed_panel(),
        "person_schema_policy": person_policy,
        "tool_entitlement_config": entitlement_config,
    }, {"service": PersonToolEntitlementRouter(event_sink=sink)})["person_tool_entitlement_panel"]
    return registry, entitlements, providers, sink
