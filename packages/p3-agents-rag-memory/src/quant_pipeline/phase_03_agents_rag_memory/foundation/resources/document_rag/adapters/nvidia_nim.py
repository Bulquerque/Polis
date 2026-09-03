from __future__ import annotations

from collections.abc import Sequence
from typing import Any


from quant_pipeline.phase_03_agents_rag_memory.shared.optional_dependencies import require_dependency

from ..canonical import content_hash
from ..errors import ErrorCategory, ProviderFailureError, error
from ..models import EmbeddingBatch, ProviderDescriptor, ProviderStatus


class NvidiaNimEmbeddingAdapter:
    """HTTP adapter for NVIDIA NeMo Retriever Embedding NIM.

    The caller owns the AsyncClient and credential lifecycle. This adapter never reads the environment.
    """

    def __init__(
        self,
        *,
        client: "httpx.AsyncClient",
        model_id: str,
        model_revision: str,
        dimensions: int | None = None,
        truncate: str = "NONE",
        credential_handle: str = "injected-client-auth",
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._model_revision = model_revision
        self._dimensions = dimensions
        self._truncate = truncate
        self._credential_handle = credential_handle

    async def describe(self) -> ProviderDescriptor:
        httpx = require_dependency("httpx", extra="api", purpose="NVIDIA NIM embedding discovery")
        try:
            response = await self._client.get("/v1/models")
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderFailureError(
                error(
                    "P3_S12_M01_EMBEDDING_PROVIDER_FAILURE",
                    ErrorCategory.PROVIDER,
                    "NVIDIA NIM model discovery failed",
                    retryable=isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)),
                    context={"provider": "nvidia_nim", "endpoint": "/v1/models"},
                )
            ) from exc
        return ProviderDescriptor(
            provider_id="nvidia_nim_embeddings",
            interface_id="EmbeddingProvider",
            adapter_id="nvidia_nim_http",
            adapter_version="1.0.0",
            status=ProviderStatus.CONNECTED_UNQUALIFIED,
            model_id=self._model_id,
            model_revision=self._model_revision,
            dimensions=self._dimensions,
            supports_batching=True,
            qualification_status="CONNECTED_REQUIRES_LIVE_QUALIFICATION",
            fingerprint=content_hash(
                {
                    "provider": "nvidia_nim",
                    "model_id": self._model_id,
                    "model_revision": self._model_revision,
                    "models_response": body,
                }
            ),
            metadata={
                "credential_handle": self._credential_handle,
                "input_type": "passage",
                "truncate": self._truncate,
            },
        )

    async def embed_passages(self, texts: Sequence[str]) -> EmbeddingBatch:
        httpx = require_dependency("httpx", extra="api", purpose="NVIDIA NIM embeddings")
        request_body: dict[str, Any] = {
            "model": self._model_id,
            "input": list(texts),
            "input_type": "passage",
            "truncate": self._truncate,
        }
        if self._dimensions is not None:
            request_body["dimensions"] = self._dimensions
        request_hash = content_hash(request_body)
        try:
            response = await self._client.post("/v1/embeddings", json=request_body)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderFailureError(
                error(
                    "P3_S12_M01_EMBEDDING_PROVIDER_FAILURE",
                    ErrorCategory.PROVIDER,
                    "NVIDIA NIM embedding request failed",
                    retryable=isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)),
                    context={"provider": "nvidia_nim", "endpoint": "/v1/embeddings"},
                )
            ) from exc
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise ProviderFailureError(
                error(
                    "P3_S12_M01_EMBEDDING_PROVIDER_FAILURE",
                    ErrorCategory.PROVIDER,
                    "NVIDIA NIM returned invalid embedding cardinality",
                    context={"expected": len(texts), "actual": len(data) if isinstance(data, list) else None},
                )
            )
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors = tuple(tuple(float(value) for value in item["embedding"]) for item in ordered)
        dimensions = len(vectors[0]) if vectors else self._dimensions
        if any(len(vector) != dimensions for vector in vectors):
            raise ProviderFailureError(
                error(
                    "P3_S12_M01_EMBEDDING_PROVIDER_FAILURE",
                    ErrorCategory.PROVIDER,
                    "NVIDIA NIM returned inconsistent embedding dimensions",
                )
            )
        descriptor = ProviderDescriptor(
            provider_id="nvidia_nim_embeddings",
            interface_id="EmbeddingProvider",
            adapter_id="nvidia_nim_http",
            adapter_version="1.0.0",
            status=ProviderStatus.CONNECTED_UNQUALIFIED,
            model_id=self._model_id,
            model_revision=self._model_revision,
            dimensions=dimensions,
            supports_batching=True,
            qualification_status="CONNECTED_REQUIRES_LIVE_QUALIFICATION",
            fingerprint=content_hash(
                {
                    "provider": "nvidia_nim",
                    "model_id": self._model_id,
                    "model_revision": self._model_revision,
                    "dimensions": dimensions,
                }
            ),
            metadata={"credential_handle": self._credential_handle, "input_type": "passage"},
        )
        return EmbeddingBatch(vectors=vectors, provider=descriptor, request_hash=request_hash)
