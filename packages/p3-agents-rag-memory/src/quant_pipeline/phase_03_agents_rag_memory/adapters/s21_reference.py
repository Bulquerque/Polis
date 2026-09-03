from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..runtime_shared.s21_errors import S21DependencyError
from ..runtime_shared.s21_hashing import content_hash
from ..runtime_shared.s21_models import (
    CognitionStage,
    LLMRequest,
    LLMResponse,
    ToolErrorRecord,
    ToolExecutionResponse,
    ToolExecutionStatus,
    ValidatedToolCallRequestRecord,
)
from ..runtime_shared.s21_ports import MCPClientSessionFactory


class SystemClock:
    """Production clock adapter. Tests should use FixedClock."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(slots=True)
class FixedClock:
    current: datetime
    monotonic_value: float = 0.0
    monotonic_step: float = 0.01

    def now(self) -> datetime:
        if self.current.tzinfo is None or self.current.utcoffset() is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        return self.current.astimezone(timezone.utc)

    def monotonic(self) -> float:
        value = self.monotonic_value
        self.monotonic_value += self.monotonic_step
        return value


class ScriptedLLMAdapter:
    """Deterministic adapter for tests, replay, and local integration."""

    def __init__(
        self,
        responses: Mapping[tuple[CognitionStage, str], tuple[dict[str, object], ...]],
    ) -> None:
        self._responses = {
            key: deque(value) for key, value in responses.items()
        }
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        key = (request.stage, request.cognition_transaction_id)
        queue = self._responses.get(key)
        if queue is None or not queue:
            raise S21DependencyError(
                code="SCRIPTED_LLM_RESPONSE_MISSING",
                message="no scripted LLM response exists for this stage and transaction",
                module_id="P3.S21",
                details={"stage": request.stage.value, "transaction": key[1]},
            )
        content = queue.popleft()
        return LLMResponse(
            provider_id=request.provider_id,
            model_id=request.model_id,
            content=content,
            response_hash=content_hash(content),
            raw_response_ref=f"memory://llm/{request.cognition_transaction_id}/{request.stage.value}",
        )


ToolHandler = Callable[[ValidatedToolCallRequestRecord], ToolExecutionResponse]


class InMemoryToolGatewayAdapter:
    """Deterministic tool gateway for tests and offline replay."""

    def __init__(self, handlers: Mapping[tuple[str, str], ToolHandler]) -> None:
        self._handlers = dict(handlers)
        self.requests: list[ValidatedToolCallRequestRecord] = []

    async def execute(
        self, request: ValidatedToolCallRequestRecord
    ) -> ToolExecutionResponse:
        self.requests.append(request)
        key = (request.request.tool_id, request.request.operation_id)
        handler = self._handlers.get(key)
        if handler is None:
            return ToolExecutionResponse(
                status=ToolExecutionStatus.FAILED_PROVIDER,
                provider_id=request.provider_id or "UNRESOLVED",
                error=ToolErrorRecord(
                    code="HANDLER_NOT_REGISTERED",
                    message=f"no in-memory handler for {key}",
                    retryable=False,
                ),
            )
        return handler(request)


MCPResultMapper = Callable[
    [object, ValidatedToolCallRequestRecord], ToolExecutionResponse
]


class MCPV1ToolGatewayAdapter:
    """Thin MCP v1 adapter kept behind the ToolGatewayPort.

    The caller supplies session factories and a result mapper so transport and SDK
    result types never leak into the Phase 3 domain. This follows the stable v1
    `ClientSession.call_tool` boundary while remaining transport-independent.
    """

    def __init__(
        self,
        *,
        session_factories: Mapping[str, MCPClientSessionFactory],
        result_mapper: MCPResultMapper,
    ) -> None:
        self._session_factories = dict(session_factories)
        self._result_mapper = result_mapper

    async def execute(
        self, request: ValidatedToolCallRequestRecord
    ) -> ToolExecutionResponse:
        provider_id = request.provider_id
        if provider_id is None or provider_id not in self._session_factories:
            raise S21DependencyError(
                code="MCP_SESSION_FACTORY_MISSING",
                message="no MCP session factory is registered for the provider",
                module_id="P3.S21.M03",
                details={"provider_id": provider_id},
            )
        factory = self._session_factories[provider_id]
        async with factory() as session:
            result = await session.call_tool(
                request.request.operation_id,
                request.request.arguments,
            )
        return self._result_mapper(result, request)


class FilePromptCatalog:
    """Load immutable prompt definitions from a YAML catalog and Markdown files."""

    def __init__(self, *, package_root: Path, catalog_path: Path) -> None:
        from ..runtime_shared.s21_models import PromptTemplate

        payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("prompts"), list):
            raise S21DependencyError(
                code="PROMPT_CATALOG_INVALID",
                message="prompt catalog is not a valid mapping with a prompts list",
                module_id="P3.S21",
            )
        prompts: dict[tuple[str, str], PromptTemplate] = {}
        for row in payload["prompts"]:
            if not isinstance(row, dict):
                raise S21DependencyError(
                    code="PROMPT_CATALOG_ENTRY_INVALID",
                    message="prompt catalog entry is not an object",
                    module_id="P3.S21",
                )
            prompt_id = str(row.get("prompt_id", ""))
            version = str(row.get("prompt_version", ""))
            relative_path = str(row.get("path", ""))
            path = (package_root / relative_path).resolve()
            if package_root.resolve() not in path.parents or not path.is_file():
                raise S21DependencyError(
                    code="PROMPT_FILE_MISSING_OR_OUTSIDE_ROOT",
                    message="prompt file is missing or outside the package root",
                    module_id="P3.S21",
                    details={"path": relative_path},
                )
            text = path.read_text(encoding="utf-8").strip()
            prompts[(prompt_id, version)] = PromptTemplate(
                prompt_id=prompt_id,
                prompt_version=version,
                system_prompt=text,
                prompt_hash=content_hash(text),
            )
        self._prompts = prompts

    def get(self, prompt_id: str, prompt_version: str):
        prompt = self._prompts.get((prompt_id, prompt_version))
        if prompt is None:
            raise S21DependencyError(
                code="PROMPT_NOT_REGISTERED",
                message="prompt ID/version is absent from the prompt catalog",
                module_id="P3.S21",
                details={"prompt_id": prompt_id, "prompt_version": prompt_version},
            )
        return prompt


class InMemoryPromptCatalog:
    """Immutable prompt catalog for tests, replay, and composition roots."""

    def __init__(self, prompts: Mapping[tuple[str, str], str]) -> None:
        from ..runtime_shared.s21_models import PromptTemplate

        self._prompts = {
            key: PromptTemplate(
                prompt_id=key[0],
                prompt_version=key[1],
                system_prompt=value,
                prompt_hash=content_hash(value),
            )
            for key, value in prompts.items()
        }

    def get(self, prompt_id: str, prompt_version: str):
        key = (prompt_id, prompt_version)
        prompt = self._prompts.get(key)
        if prompt is None:
            raise S21DependencyError(
                code="PROMPT_NOT_REGISTERED",
                message="prompt ID/version is absent from the prompt catalog",
                module_id="P3.S21",
                details={"prompt_id": prompt_id, "prompt_version": prompt_version},
            )
        return prompt
