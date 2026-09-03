from __future__ import annotations

from collections.abc import Mapping

from .s21_errors import S21ContractError
from .s21_hashing import canonical_json
from .s21_models import (
    BeliefValueType,
    ProviderAdapterRegistryConfig,
    PropositionRegistryConfig,
)


JsonMapping = Mapping[str, object]


def resolve_provider_registry(
    *,
    global_registry: JsonMapping,
    s21_resolution: JsonMapping,
) -> ProviderAdapterRegistryConfig:
    """Resolve the descriptive global provider registry into S21 runtime config.

    The global registry remains authoritative for permitted interfaces. The S21
    resolution file selects concrete adapters/models without modifying that global
    document.
    """
    interfaces = global_registry.get("interfaces")
    if not isinstance(interfaces, list):
        raise S21ContractError(
            code="GLOBAL_PROVIDER_REGISTRY_INVALID",
            message="global provider registry has no interface list",
            module_id="P3.S21",
        )
    interface_ids = {
        item.get("interface_id")
        for item in interfaces
        if isinstance(item, dict)
    }
    required = {"LLMProviderAdapter", "MCPGatewayAdapter"}
    missing = required - interface_ids
    if missing:
        raise S21ContractError(
            code="REQUIRED_PROVIDER_INTERFACE_MISSING",
            message="global provider registry does not authorize required S21 interfaces",
            module_id="P3.S21",
            details={"missing_interfaces": sorted(missing)},
        )
    return ProviderAdapterRegistryConfig.model_validate_json(
        canonical_json(s21_resolution)
    )


def resolve_proposition_registry(
    *,
    global_registry: JsonMapping,
    s21_semantics: JsonMapping,
) -> PropositionRegistryConfig:
    """Merge global proposition IDs/horizons with S21 typed value semantics."""
    global_rows = global_registry.get("propositions")
    semantic_rows = s21_semantics.get("propositions")
    if not isinstance(global_rows, list) or not isinstance(semantic_rows, list):
        raise S21ContractError(
            code="PROPOSITION_REGISTRY_INVALID",
            message="global or S21 proposition registry has no proposition list",
            module_id="P3.S21.M06",
        )
    global_by_id = {
        row.get("proposition_id"): row for row in global_rows if isinstance(row, dict)
    }
    resolved: list[dict[str, object]] = []
    for semantic in semantic_rows:
        if not isinstance(semantic, dict):
            continue
        proposition_id = semantic.get("proposition_id")
        global_row = global_by_id.get(proposition_id)
        if global_row is None:
            raise S21ContractError(
                code="S21_PROPOSITION_NOT_GLOBALLY_REGISTERED",
                message="S21 semantics reference an unknown global proposition",
                module_id="P3.S21.M06",
                details={"proposition_id": proposition_id},
            )
        row = dict(semantic)
        row["allowed_horizons"] = global_row.get("allowed_horizons", [])
        resolved.append(row)
    resolved_payload = {
        "schema_version": "p3.s21.v1",
        "registry_version": str(s21_semantics.get("registry_version", "1.0.0")),
        "propositions": resolved,
    }
    return PropositionRegistryConfig.model_validate_json(
        canonical_json(resolved_payload)
    )


DEFAULT_PROPOSITION_VALUE_TYPES: dict[str, BeliefValueType] = {
    "directional_outlook": BeliefValueType.DIRECTIONAL_SCORE,
    "volatility_outlook": BeliefValueType.VOLATILITY_LEVEL,
    "regime_outlook": BeliefValueType.REGIME_PROBABILITIES,
}
