from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import AsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .s21_models import (
    LLMRequest,
    LLMResponse,
    PromptTemplate,
    ToolExecutionResponse,
    ValidatedToolCallRequestRecord,
)


class LLMPort(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate one schema-constrained response."""


class PromptCatalogPort(Protocol):
    def get(self, prompt_id: str, prompt_version: str) -> PromptTemplate:
        """Return one immutable, versioned prompt template."""


class ToolGatewayPort(Protocol):
    async def execute(
        self, request: ValidatedToolCallRequestRecord
    ) -> ToolExecutionResponse:
        """Execute one previously authorized tool request."""


class ClockPort(Protocol):
    def now(self) -> datetime:
        """Return a timezone-aware current time."""

    def monotonic(self) -> float:
        """Return a monotonic time suitable for latency measurement."""


class MCPClientSessionPort(Protocol):
    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> object:
        """Call a tool using an MCP client session."""


MCPClientSessionFactory = Callable[[], AsyncContextManager[MCPClientSessionPort]]


@dataclass(frozen=True, slots=True)
class S21Runtime:
    llm: LLMPort
    tool_gateway: ToolGatewayPort
    clock: ClockPort
    prompts: PromptCatalogPort
