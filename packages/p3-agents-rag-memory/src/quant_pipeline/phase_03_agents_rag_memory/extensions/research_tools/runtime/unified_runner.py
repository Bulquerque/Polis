"""Single-transaction execution for the complete research-tools gateway."""
from __future__ import annotations

import asyncio
import importlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash, utc
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ToolExecutionResponse,
    ToolExecutionStatus,
    ValidatedToolCallRequestRecord,
)

if TYPE_CHECKING:
    from .gateway import CompositeResearchToolGateway


class UnifiedToolDriver(Protocol):
    """External composition contract for the one-command runner."""

    def prepare(self, config: dict[str, Any], output_dir: Path) -> dict[str, Any]: ...


@dataclass(frozen=True)
class UnifiedToolExecution:
    """Stable summary of one operation inside a unified run."""

    tool_id: str
    operation_id: str
    status: str
    response_hash: str | None
    error_code: str | None
    error_message: str | None

    @classmethod
    def from_response(
        cls,
        request: ValidatedToolCallRequestRecord,
        response: ToolExecutionResponse,
    ) -> "UnifiedToolExecution":
        error = response.error
        return cls(
            tool_id=request.request.tool_id,
            operation_id=request.request.operation_id,
            status=response.status.value,
            response_hash=response.response_hash,
            error_code=error.code if error else None,
            error_message=error.message if error else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "operation_id": self.operation_id,
            "status": self.status,
            "response_hash": self.response_hash,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class UnifiedResearchToolsReceipt:
    """Content-addressed receipt for one complete gateway execution."""

    run_id: str
    cycle_id: str
    decision_time: datetime
    snapshot_id: str
    status: str
    operation_count: int
    succeeded_count: int
    failed_count: int
    family_counts: dict[str, int]
    executions: tuple[UnifiedToolExecution, ...]
    receipt_hash: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "receipt_version": "p3.research-tools.unified-run.v1",
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "decision_time": utc(self.decision_time),
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "operation_count": self.operation_count,
            "succeeded_count": self.succeeded_count,
            "failed_count": self.failed_count,
            "family_counts": dict(sorted(self.family_counts.items())),
            "executions": [item.as_dict() for item in self.executions],
        }

    def as_dict(self) -> dict[str, Any]:
        payload = self.unsigned_dict()
        payload["receipt_hash"] = self.receipt_hash
        return payload


def _family(tool_id: str) -> str:
    """Return the stable family segment from a canonical tool identifier."""
    families = {
        "research.corpus.v1": "corpus",
        "market.observation.v1": "market",
        "options.observation.v1": "options",
        "macro.observation.v1": "macro",
        "company.fundamentals.v1": "company",
        "quant.diagnostics.v1": "quant",
    }
    try:
        return families[tool_id]
    except KeyError as exc:
        raise ValueError(f"unsupported research-tool family: {tool_id}") from exc


def _validate_batch(
    requests: Sequence[ValidatedToolCallRequestRecord],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: datetime,
    snapshot_id: str,
) -> tuple[ValidatedToolCallRequestRecord, ...]:
    values = tuple(requests)
    for name, value in (
        ("run_id", run_id),
        ("cycle_id", cycle_id),
        ("snapshot_id", snapshot_id),
    ):
        if not value.strip():
            raise ValueError(f"{name} must be non-empty")
    utc(decision_time)
    keys = [(item.request.tool_id, item.request.operation_id) for item in values]
    if len(keys) != len(set(keys)):
        raise ValueError("unified tool batch cannot contain duplicate operations")
    return values


async def execute_unified_batch(
    gateway: "CompositeResearchToolGateway",
    requests: Sequence[ValidatedToolCallRequestRecord],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: datetime,
    snapshot_id: str,
) -> UnifiedResearchToolsReceipt:
    """Execute all requests sequentially and return one deterministic receipt.

    Sequential dispatch is intentional: it gives the audit trail one stable order,
    one transaction boundary and no cross-family concurrency ambiguity.
    Individual failures are preserved in the receipt; the batch status is ``FAIL``
    whenever any operation fails or succeeds without a response hash.
    """
    batch = _validate_batch(
        requests,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        snapshot_id=snapshot_id,
    )
    executions: list[UnifiedToolExecution] = []
    for request in batch:
        response = await gateway.execute(request)
        execution = UnifiedToolExecution.from_response(request, response)
        if response.status is ToolExecutionStatus.SUCCEEDED and not response.response_hash:
            execution = UnifiedToolExecution(
                tool_id=execution.tool_id,
                operation_id=execution.operation_id,
                status=ToolExecutionStatus.FAILED_SCHEMA.value,
                response_hash=None,
                error_code="P3RT-RUN-RESPONSE-HASH-MISSING",
                error_message="successful operation did not return a response hash",
            )
        executions.append(execution)

    succeeded = sum(item.status == ToolExecutionStatus.SUCCEEDED.value for item in executions)
    failed = len(executions) - succeeded
    unsigned = {
        "receipt_version": "p3.research-tools.unified-run.v1",
        "run_id": run_id,
        "cycle_id": cycle_id,
        "decision_time": utc(decision_time),
        "snapshot_id": snapshot_id,
        "status": "PASS" if failed == 0 else "FAIL",
        "operation_count": len(executions),
        "succeeded_count": succeeded,
        "failed_count": failed,
        "family_counts": dict(sorted(Counter(_family(item.tool_id) for item in executions).items())),
        "executions": [item.as_dict() for item in executions],
    }
    return UnifiedResearchToolsReceipt(
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=utc(decision_time),
        snapshot_id=snapshot_id,
        status=str(unsigned["status"]),
        operation_count=len(executions),
        succeeded_count=succeeded,
        failed_count=failed,
        family_counts=dict(unsigned["family_counts"]),
        executions=tuple(executions),
        receipt_hash=content_hash(unsigned),
    )


def execute_unified_batch_sync(
    gateway: "CompositeResearchToolGateway",
    requests: Sequence[ValidatedToolCallRequestRecord],
    **kwargs: Any,
) -> UnifiedResearchToolsReceipt:
    """Synchronous entrypoint for one unified run outside an active event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(execute_unified_batch(gateway, requests, **kwargs))
    raise RuntimeError("execute_unified_batch_sync() cannot run inside an active event loop")


def run_unified_driver(
    reference: str,
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Compose a gateway once, execute one batch and persist one receipt."""
    if ":" not in reference:
        raise ValueError("driver must use module:factory")
    module_name, factory_name = reference.split(":", 1)
    factory = getattr(importlib.import_module(module_name), factory_name)
    driver = factory()
    if not hasattr(driver, "prepare"):
        raise TypeError("unified tool driver must expose prepare(config, output_dir)")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("unified tool runner config must be a JSON object")
    prepared = driver.prepare(config, output_path.parent)
    if not isinstance(prepared, dict):
        raise TypeError("unified tool driver prepare() must return a mapping")
    required = {"gateway", "requests", "run_id", "cycle_id", "decision_time", "snapshot_id"}
    missing = sorted(required - set(prepared))
    if missing:
        raise KeyError(f"unified tool driver missing fields: {', '.join(missing)}")
    decision_time = prepared["decision_time"]
    if isinstance(decision_time, str):
        decision_time = datetime.fromisoformat(decision_time.replace("Z", "+00:00"))
    receipt = execute_unified_batch_sync(
        prepared["gateway"],
        prepared["requests"],
        run_id=str(prepared["run_id"]),
        cycle_id=str(prepared["cycle_id"]),
        decision_time=decision_time,
        snapshot_id=str(prepared["snapshot_id"]),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(canonical_json(receipt.as_dict()) + "\n", encoding="utf-8")
    return {"status": receipt.status, "receipt": receipt.as_dict(), "output_path": str(output_path.resolve())}
