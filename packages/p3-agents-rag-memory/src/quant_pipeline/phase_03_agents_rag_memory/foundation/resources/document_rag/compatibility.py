from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError

from .errors import ErrorCategory, InputContractError, error
from .models import (
    EmbeddingSettings,
    PitValidatedContext,
    ProviderDescriptor,
    ProviderRegistry,
    ProviderStatus,
    RetrievalConfig,
    RerankerSettings,
    RunSnapshot,
)


def normalize_pit_context(payload: dict[str, Any]) -> PitValidatedContext:
    data = dict(payload)
    data.setdefault("schema_id", "pit_validated_context.s12.v1")
    data.setdefault("schema_version", "1.0.0")
    data.setdefault("lineage_id", str(payload.get("lineage_id", "compatibility-pit-context")))
    try:
        return PitValidatedContext.model_validate(data, strict=False)
    except ValidationError as exc:
        raise InputContractError(
            error(
                "P3_S12_M01_INPUT_INVALID",
                ErrorCategory.CONTRACT,
                "pit_validated_context does not satisfy the S12 document handoff contract",
                context={"validation_errors": exc.errors(include_input=False)},
            )
        ) from exc


def normalize_run_snapshot(payload: dict[str, Any]) -> RunSnapshot:
    data = dict(payload)
    if "items" in data and "run_id" not in data:
        flattened: dict[str, Any] = {}
        for item in data.get("items", []):
            if isinstance(item, dict) and "key" in item and "value" in item:
                flattened[str(item["key"])] = item["value"]
            elif isinstance(item, dict):
                flattened.update(item)
        flattened.setdefault("schema_version", data.get("schema_version", "1.0.0"))
        flattened.setdefault("schema_id", "phase3_run_snapshot.s12.v1")
        data = flattened
    data.setdefault("schema_id", "phase3_run_snapshot.s12.v1")
    data.setdefault("schema_version", "1.0.0")
    data.setdefault("timezone", "UTC")
    try:
        return RunSnapshot.model_validate(data, strict=False)
    except ValidationError as exc:
        raise InputContractError(
            error(
                "P3_S12_M01_INPUT_INVALID",
                ErrorCategory.CONTRACT,
                "phase3_run_snapshot lacks the fields required for reproducible S12 indexing",
                context={"validation_errors": exc.errors(include_input=False)},
            )
        ) from exc


def normalize_retrieval_config(payload: dict[str, Any]) -> RetrievalConfig:
    if "chunking" in payload or "embedding" in payload:
        return RetrievalConfig.model_validate(payload, strict=False)
    # Explicit compatibility adapter for the original shallow P3-FINAL config.
    semantic_weight = float(payload.get("hybrid_weights", {}).get("semantic", 0.0))
    embedding = EmbeddingSettings(
        enabled=semantic_weight > 0,
        semantic_required=False,
        provider_id="offline_hashing",
    )
    reranker = RerankerSettings(
        enabled=bool(payload.get("reranker_required_when_connected", False)),
        provider_id=None,
        required_when_connected=bool(payload.get("reranker_required_when_connected", True)),
    )
    return RetrievalConfig(embedding=embedding, reranker=reranker)


def normalize_provider_registry(payload: dict[str, Any]) -> ProviderRegistry:
    if "providers" in payload:
        return ProviderRegistry.model_validate(payload, strict=False)
    providers: list[ProviderDescriptor] = []
    reference = payload.get("reference_profiles", {}).get("nvidia_first", {})
    if reference.get("embeddings"):
        providers.append(
            ProviderDescriptor(
                provider_id="nvidia_nim_embeddings",
                interface_id="EmbeddingProvider",
                adapter_id="nvidia_nim_http",
                adapter_version="1.0.0",
                status=ProviderStatus.CONFIGURED_DISCONNECTED,
                model_id=None,
                model_revision=None,
                supports_batching=True,
                qualification_status="UNQUALIFIED_NOT_CONNECTED",
                fingerprint="compatibility-registry-nvidia-embedding",
            )
        )
    if reference.get("reranker"):
        providers.append(
            ProviderDescriptor(
                provider_id="nvidia_nim_reranker",
                interface_id="RerankerProvider",
                adapter_id="nvidia_nim_http",
                adapter_version="1.0.0",
                status=ProviderStatus.CONFIGURED_DISCONNECTED,
                model_id=None,
                model_revision=None,
                supports_batching=True,
                qualification_status="UNQUALIFIED_NOT_CONNECTED",
                fingerprint="compatibility-registry-nvidia-reranker",
            )
        )
    return ProviderRegistry(providers=tuple(providers))
