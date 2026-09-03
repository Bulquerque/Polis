from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Literal


from quant_pipeline.phase_03_agents_rag_memory.shared.optional_dependencies import require_dependency

from quant_pipeline.phase_03_agents_rag_memory.adapters.nim_endpoint import (
    normalize_nvidia_nim_endpoint,
)
from ..canonical import content_hash
from ..errors import ErrorCategory, ProviderFailureError, error
from ..models import GraphProposalBatch, ProviderDescriptor, ProviderStatus


class DisabledGraphProposalProvider:
    def __init__(self, provider_id: str = "disabled_graph_proposals") -> None:
        self._provider_id = provider_id

    async def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self._provider_id,
            interface_id="GraphProposalProvider",
            adapter_id="disabled_graph_proposals",
            adapter_version="1.0.0",
            status=ProviderStatus.DISABLED,
            supports_json_schema=False,
            supports_batching=False,
            supports_temporal_metadata=False,
            supports_snapshot_pin=True,
            qualification_status="DISABLED",
            fingerprint=content_hash({"provider": self._provider_id, "status": "disabled"}),
        )

    async def propose(self, chunks: Sequence[dict[str, object]]) -> GraphProposalBatch:
        return GraphProposalBatch()


class StaticGraphProposalProvider:
    def __init__(self, batch: GraphProposalBatch, provider_id: str = "static_graph_proposals") -> None:
        self._batch = batch
        self._provider_id = provider_id

    async def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self._provider_id,
            interface_id="GraphProposalProvider",
            adapter_id="static_graph_proposals",
            adapter_version="1.0.0",
            status=ProviderStatus.CONNECTED_QUALIFIED,
            model_id="fixture",
            model_revision="1",
            supports_json_schema=True,
            supports_batching=True,
            supports_temporal_metadata=False,
            supports_snapshot_pin=True,
            qualification_status="QUALIFIED_LOCAL_FIXTURE_ONLY",
            fingerprint=content_hash({"provider": self._provider_id, "batch": self._batch}),
        )

    async def propose(self, chunks: Sequence[dict[str, object]]) -> GraphProposalBatch:
        return self._batch


class NvidiaNimGraphProposalProvider:
    """Optional NVIDIA NIM adapter with version-aware structured output modes."""

    def __init__(
        self,
        *,
        client: "httpx.AsyncClient",
        base_url: str,
        model_id: str,
        model_revision: str,
        provider_id: str = "nvidia_nim_graph",
        structured_mode: Literal["guided_json", "response_format_json_schema"] = "guided_json",
        max_tokens: int = 2048,
    ) -> None:
        self._client = client
        self._endpoint_url = normalize_nvidia_nim_endpoint(base_url)
        self._model_id = model_id
        self._model_revision = model_revision
        self._provider_id = provider_id
        self._structured_mode = structured_mode
        self._max_tokens = max_tokens

    async def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self._provider_id,
            interface_id="GraphProposalProvider",
            adapter_id="nvidia_nim_structured_graph",
            adapter_version="1.1.0",
            status=ProviderStatus.CONNECTED_UNQUALIFIED,
            model_id=self._model_id,
            model_revision=self._model_revision,
            supports_json_schema=True,
            supports_batching=True,
            supports_temporal_metadata=False,
            supports_snapshot_pin=True,
            qualification_status="IMPLEMENTED_UNQUALIFIED_LIVE_PROVIDER",
            fingerprint=content_hash(
                {
                    "provider": self._provider_id,
                    "model": self._model_id,
                    "revision": self._model_revision,
                    "endpoint_url": self._endpoint_url,
                    "structured_mode": self._structured_mode,
                    "max_tokens": self._max_tokens,
                }
            ),
            metadata={"structured_mode": self._structured_mode},
        )

    async def propose(
        self,
        chunks: Sequence[dict[str, object]],
    ) -> GraphProposalBatch:
        httpx = require_dependency("httpx", extra="api", purpose="NVIDIA NIM GraphRAG proposals")
        schema = GraphProposalBatch.model_json_schema()
        payload: dict[str, Any] = {
            "model": self._model_id,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Propose only evidence-bound graph nodes and relations. "
                        "Every proposal must cite existing chunk_ids. "
                        "Do not infer facts not supported by the supplied chunks."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"chunks": list(chunks)},
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        if self._structured_mode == "guided_json":
            payload["guided_json"] = schema
        else:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "graph_proposal_batch",
                    "strict": True,
                    "schema": schema,
                },
            }
        try:
            response = await self._client.post(
                self._endpoint_url,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            if choice.get("finish_reason") not in {None, "stop"}:
                raise ValueError("NIM response did not finish cleanly")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("NIM response content must be a JSON string")
            return GraphProposalBatch.model_validate_json(content, strict=True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderFailureError(
                error(
                    "P3_S13_M01_PROVIDER_FAILURE",
                    ErrorCategory.PROVIDER,
                    "NVIDIA NIM graph proposal request failed",
                    context={"provider_id": self._provider_id},
                )
            ) from exc
