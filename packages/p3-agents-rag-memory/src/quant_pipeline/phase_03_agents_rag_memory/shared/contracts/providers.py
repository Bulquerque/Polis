from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .base import StrictModel


class ProviderAdapterDescriptor(StrictModel):
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    protocol: str
    protocol_version: str
    connectivity_status: Literal["CONNECTED", "DISCONNECTED", "INTERFACE_ONLY", "LOCAL"]
    qualification_status: str
    capabilities: tuple[str, ...]
    timeout_seconds: float = Field(gt=0.0, le=300.0)
    max_concurrency: int = Field(ge=1, le=1000)
    retryable_status_codes: tuple[int, ...] = (429, 502, 503, 504)
    pit_policy: str
    credential_handle: str | None = None
    model_id: str | None = None
    model_revision: str | None = None
    observed_at: datetime | None = None
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("observed_at")
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("observed_at must be timezone-aware")
        return value


class ProviderAdapterRegistry(StrictModel):
    schema_id: Literal["provider_adapter_registry.v2"] = "provider_adapter_registry.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    registry_id: str
    adapters: tuple[ProviderAdapterDescriptor, ...]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def find(self, provider_id: str, interface_id: str) -> ProviderAdapterDescriptor | None:
        return next((item for item in self.adapters if item.provider_id == provider_id and item.interface_id == interface_id), None)
