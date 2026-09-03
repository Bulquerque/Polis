from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..transport.credentials import CredentialResolver
from ..transport.http_client import HttpClient, TransportResponse


class AdapterConfigurationError(RuntimeError):
    pass


@dataclass
class AdapterContext:
    credential_resolver: CredentialResolver
    http_client: HttpClient


class SourceAdapter:
    adapter_id = "base"

    def health_check(self, task: dict, context: AdapterContext) -> bool:
        return True

    def discover(self, source: dict, context: AdapterContext) -> list[dict]:
        return list(source.get("datasets") or [])

    def plan_tasks(self, source: dict, context: AdapterContext) -> list[dict]:
        return []

    def fetch_raw(self, task: dict, context: AdapterContext) -> list[TransportResponse]:
        raise NotImplementedError
