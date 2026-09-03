"""Vendor-neutral provider port and request/response models."""
from __future__ import annotations

from typing import Protocol
from pydantic import Field
from .models import ProviderKind, ProviderUsage, StrictModel

class ProviderMessage(StrictModel):
    role: str
    content: str

class StructuredGenerationRequest(StrictModel):
    provider_id: str
    provider_kind: ProviderKind
    model_id: str
    messages: tuple[ProviderMessage, ...]
    json_schema_name: str
    json_schema: dict[str, object]
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(gt=0)
    seed: int
    request_hash: str

class StructuredGenerationResponse(StrictModel):
    content: str
    provider_request_id: str | None = None
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    cache_hit: bool = False

class StructuredLLMPort(Protocol):
    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse:
        """Return one structured response or raise a typed provider error."""
