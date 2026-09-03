"""HTTPX adapters for supported structured-output APIs.

The domain imports only StructuredLLMPort. These adapters contain all provider-specific
payload details and are fully testable with httpx.MockTransport.
"""
from __future__ import annotations

import json
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.shared.optional_dependencies import require_dependency

from .errors import NonRetryableProviderError, RetryableProviderError
from .models import ProviderKind, ProviderUsage
from .ports import StructuredGenerationRequest, StructuredGenerationResponse

class OpenAICompatibleStructuredAdapter:
    def __init__(
        self,
        client: "httpx.AsyncClient",
        *,
        provider_kind: ProviderKind,
        api_key: str | None,
        retryable_status_codes: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504}),
    ) -> None:
        self._client = client
        self._provider_kind = provider_kind
        self._api_key = api_key
        self._retryable_status_codes = retryable_status_codes

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse:
        httpx = require_dependency("httpx", extra="api", purpose="structured LLM HTTP adapters")
        if request.provider_kind is not self._provider_kind:
            raise NonRetryableProviderError("provider kind mismatch")
        payload = self._payload(request)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._client.post(
                "/chat/completions",
                headers=headers,
                json=payload,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RetryableProviderError(type(exc).__name__) from exc

        if response.status_code in self._retryable_status_codes:
            raise RetryableProviderError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise NonRetryableProviderError(f"HTTP {response.status_code}")
        try:
            body: dict[str, Any] = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message.content must be a string")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise NonRetryableProviderError("invalid provider response envelope") from exc
        usage_raw = body.get("usage") or {}
        usage = ProviderUsage(
            prompt_tokens=self._optional_int(usage_raw.get("prompt_tokens")),
            completion_tokens=self._optional_int(usage_raw.get("completion_tokens")),
            total_tokens=self._optional_int(usage_raw.get("total_tokens")),
        )
        return StructuredGenerationResponse(
            content=content,
            provider_request_id=(
                response.headers.get("x-request-id")
                or (str(body.get("id")) if body.get("id") else None)
            ),
            usage=usage,
        )

    def _payload(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        common: dict[str, Any] = {
            "model": request.model_id,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "seed": request.seed,
            "stream": False,
        }
        if self._provider_kind is ProviderKind.NVIDIA_NIM:
            common["guided_json"] = request.json_schema
        elif self._provider_kind is ProviderKind.HUGGINGFACE_ROUTER:
            common["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.json_schema_name,
                    "schema": request.json_schema,
                    "strict": True,
                },
            }
        else:
            raise NonRetryableProviderError("unsupported provider kind")
        return common

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None
