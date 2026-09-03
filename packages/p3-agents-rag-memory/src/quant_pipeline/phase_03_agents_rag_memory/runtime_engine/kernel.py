from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .errors import BoundaryValidationError
from .contracts_internal import (
    ArtifactPointer,
    CycleKernelRequest,
    CycleKernelResult,
    ExecutionMode,
    ExecutionStatus,
    ModuleTraceEntry,
    P3CycleClosureManifest,
    RuntimeFoundationContext,
    RuntimeIssue,
    ToolAuditEntry,
)
from .ports import CycleCapabilityPort, FoundationManifestResolverPort
from .registry import module_ids_for_mode

_STATUS_RANK = {
    ExecutionStatus.READY: 0,
    ExecutionStatus.EMPTY_VALID: 0,
    ExecutionStatus.SKIPPED_NOT_APPLICABLE: 0,
    ExecutionStatus.DEGRADED: 1,
    ExecutionStatus.BLOCKED: 2,
    ExecutionStatus.FAILED: 3,
}


@dataclass(frozen=True, slots=True)
class CapabilityExecution:
    """Typed handoff between cohesive runtime capabilities."""

    artifacts: Mapping[str, ArtifactPointer] = field(default_factory=dict)
    module_trace: tuple[ModuleTraceEntry, ...] = ()
    tool_audits: tuple[ToolAuditEntry, ...] = ()
    closure_manifest: P3CycleClosureManifest | None = None
    p4_outputs: tuple[ArtifactPointer, ...] = ()
    p9_outputs: tuple[ArtifactPointer, ...] = ()
    variable_evolution_output: ArtifactPointer | None = None
    status: ExecutionStatus = ExecutionStatus.READY
    issues: tuple[RuntimeIssue, ...] = ()


@dataclass(slots=True)
class _ExecutionAccumulator:
    artifacts: dict[str, ArtifactPointer] = field(default_factory=dict)
    trace: list[ModuleTraceEntry] = field(default_factory=list)
    audits: list[ToolAuditEntry] = field(default_factory=list)
    issues: list[RuntimeIssue] = field(default_factory=list)
    statuses: list[ExecutionStatus] = field(default_factory=list)


class CycleKernel:
    """Canonical orchestrator for S17-S31 under the definitive mode policy."""

    contract_version = "1.0.0"

    def __init__(
        self,
        *,
        foundation_resolver: FoundationManifestResolverPort,
        context_capability: CycleCapabilityPort,
        cognition_capability: CycleCapabilityPort,
        closure_capability: CycleCapabilityPort,
        analytics_capability: CycleCapabilityPort | None = None,
        products_capability: CycleCapabilityPort | None = None,
        require_complete_trace: bool = False,
    ) -> None:
        self._foundation_resolver = foundation_resolver
        self._context_capability = context_capability
        self._cognition_capability = cognition_capability
        self._closure_capability = closure_capability
        self._analytics_capability = analytics_capability
        self._products_capability = products_capability
        self._require_complete_trace = require_complete_trace

    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult:
        foundation = await self._foundation_resolver.resolve(request.foundation_manifest)
        validation_issues = await self._validate(request, foundation)
        blocking = tuple(issue for issue in validation_issues if issue.severity == "ERROR")
        if request.mode is ExecutionMode.DRY_RUN:
            return self._dry_run_result(request, validation_issues, blocking)
        if blocking:
            raise BoundaryValidationError(
                "cycle capability validation failed: "
                + "; ".join(item.message for item in blocking)
            )

        state = _ExecutionAccumulator(issues=list(validation_issues))
        closure = await self._execute_core(request, foundation, state)
        await self._execute_analytics(request, foundation, state)
        p4_outputs, p9_outputs, variable_evolution_output = await self._execute_products(request, foundation, state)
        self._validate_trace_scope(
            request,
            state.trace,
            state.audits,
            require_complete=self._require_complete_trace,
        )
        return self._result(request, state, closure, p4_outputs, p9_outputs, variable_evolution_output)

    async def _execute_core(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        state: _ExecutionAccumulator,
    ) -> P3CycleClosureManifest:
        await self._execute_capability(self._context_capability, request, foundation, state)
        await self._execute_capability(self._cognition_capability, request, foundation, state)
        execution = await self._execute_capability(self._closure_capability, request, foundation, state)
        closure = execution.closure_manifest
        if closure is None:
            raise BoundaryValidationError("society closure capability must produce P3CycleClosureManifest")
        self._validate_closure(request, closure)
        return closure

    async def _execute_analytics(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        state: _ExecutionAccumulator,
    ) -> None:
        if request.mode not in {ExecutionMode.REPLAY, ExecutionMode.LIVE}:
            return
        if self._analytics_capability is None:
            raise BoundaryValidationError(f"{request.mode} requires society analytics capability")
        await self._execute_capability(self._analytics_capability, request, foundation, state)

    async def _execute_products(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        state: _ExecutionAccumulator,
    ) -> tuple[tuple[ArtifactPointer, ...], tuple[ArtifactPointer, ...], ArtifactPointer | None]:
        if request.mode is not ExecutionMode.LIVE:
            return (), (), None
        if self._products_capability is None:
            raise BoundaryValidationError("LIVE requires products capability")
        execution = await self._execute_capability(self._products_capability, request, foundation, state)
        return execution.p4_outputs, execution.p9_outputs, execution.variable_evolution_output

    async def _execute_capability(
        self,
        capability: CycleCapabilityPort,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        state: _ExecutionAccumulator,
    ) -> CapabilityExecution:
        execution = await capability.execute(request, foundation, dict(state.artifacts))
        if execution.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED}:
            detail = "; ".join(item.message for item in execution.issues) or execution.status.value
            raise BoundaryValidationError(f"capability execution stopped: {detail}")
        self._merge_artifacts(state.artifacts, execution.artifacts)
        state.trace.extend(execution.module_trace)
        state.audits.extend(execution.tool_audits)
        state.issues.extend(execution.issues)
        state.statuses.append(execution.status)
        return execution

    async def _validate(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
    ) -> tuple[RuntimeIssue, ...]:
        capabilities, missing = self._validation_capabilities(request)
        issues: list[RuntimeIssue] = list(missing)
        for capability in capabilities:
            issues.extend(await capability.validate(request, foundation))
        return tuple(issues)

    def _validation_capabilities(
        self,
        request: CycleKernelRequest,
    ) -> tuple[list[CycleCapabilityPort], list[RuntimeIssue]]:
        capabilities: list[CycleCapabilityPort] = [self._context_capability, self._cognition_capability, self._closure_capability]
        missing: list[RuntimeIssue] = []
        if request.mode in {ExecutionMode.REPLAY, ExecutionMode.LIVE, ExecutionMode.DRY_RUN}:
            self._append_optional(capabilities, missing, self._analytics_capability, "SOCIETY_ANALYTICS", request)
        if request.mode in {ExecutionMode.LIVE, ExecutionMode.DRY_RUN}:
            self._append_optional(capabilities, missing, self._products_capability, "PRODUCTS", request)
        return capabilities, missing

    @staticmethod
    def _append_optional(
        capabilities: list[CycleCapabilityPort],
        missing: list[RuntimeIssue],
        capability: CycleCapabilityPort | None,
        name: str,
        request: CycleKernelRequest,
    ) -> None:
        if capability is not None:
            capabilities.append(capability)
            return
        missing.append(
            RuntimeIssue(
                code=f"{name}_NOT_CONFIGURED",
                message=f"{name.replace('_', ' ')} capability is required for {request.mode.value}",
                severity="ERROR",
            )
        )

    @staticmethod
    def _dry_run_result(
        request: CycleKernelRequest,
        issues: tuple[RuntimeIssue, ...],
        blocking: tuple[RuntimeIssue, ...],
    ) -> CycleKernelResult:
        status = ExecutionStatus.BLOCKED if blocking else ExecutionStatus.DEGRADED if issues else ExecutionStatus.READY
        return CycleKernelResult(
            request_id=request.request_id,
            mode=request.mode,
            status=status,
            closure_manifest=None,
            module_trace=(),
            issues=issues,
        )

    @classmethod
    def _result(
        cls,
        request: CycleKernelRequest,
        state: _ExecutionAccumulator,
        closure: P3CycleClosureManifest,
        p4_outputs: tuple[ArtifactPointer, ...],
        p9_outputs: tuple[ArtifactPointer, ...],
        variable_evolution_output: ArtifactPointer | None,
    ) -> CycleKernelResult:
        return CycleKernelResult(
            request_id=request.request_id,
            mode=request.mode,
            status=cls._aggregate_status(state.statuses, state.issues),
            closure_manifest=closure,
            module_trace=tuple(state.trace),
            tool_audits=tuple(state.audits),
            p4_outputs=p4_outputs,
            p9_outputs=p9_outputs,
            variable_evolution_output=variable_evolution_output,
            issues=tuple(state.issues),
        )

    @staticmethod
    def _validate_closure(request: CycleKernelRequest, closure: P3CycleClosureManifest) -> None:
        if closure.run_id != request.run_id or closure.snapshot_id != request.snapshot_id:
            raise BoundaryValidationError("closure identity does not match cycle request")
        if closure.source_cycle_id != request.cycle_id:
            raise BoundaryValidationError("closure source_cycle_id does not match request cycle_id")
        if closure.as_of_time != request.as_of_time:
            raise BoundaryValidationError("closure cutoff does not match cycle request")

    @staticmethod
    def _validate_trace_scope(
        request: CycleKernelRequest,
        trace: list[ModuleTraceEntry],
        audits: list[ToolAuditEntry],
        *,
        require_complete: bool,
    ) -> None:
        seen: set[str] = set()
        max_subphase = 26 if request.mode is ExecutionMode.WARMUP_REPLAY else 28 if request.mode is ExecutionMode.REPLAY else 31
        for item in trace:
            CycleKernel._validate_trace_item(request, item, seen, max_subphase)
        if any(audit.available_at > request.as_of_time for audit in audits):
            raise BoundaryValidationError("tool audit contains information after the cycle cutoff")
        if require_complete:
            expected = module_ids_for_mode(request.mode.value)
            observed = tuple(item.module_id for item in trace)
            if observed != expected:
                missing = tuple(module_id for module_id in expected if module_id not in observed)
                unexpected = tuple(module_id for module_id in observed if module_id not in expected)
                raise BoundaryValidationError(
                    "production trace is incomplete or out of order; "
                    f"missing={missing}, unexpected={unexpected}"
                )

    @staticmethod
    def _validate_trace_item(
        request: CycleKernelRequest,
        item: ModuleTraceEntry,
        seen: set[str],
        max_subphase: int,
    ) -> None:
        if item.module_id in seen:
            raise BoundaryValidationError(f"duplicate module trace entry: {item.module_id}")
        seen.add(item.module_id)
        if item.cycle_id != request.cycle_id:
            raise BoundaryValidationError(f"trace cycle_id does not match request: {item.module_id}")
        if item.as_of_time != request.as_of_time:
            raise BoundaryValidationError(f"trace cutoff does not match request: {item.module_id}")
        subphase = int(item.module_id.split(".")[1][1:])
        if subphase < 17 or subphase > max_subphase:
            raise BoundaryValidationError(
                f"module {item.module_id} is outside {request.mode.value} execution scope"
            )

    @staticmethod
    def _aggregate_status(
        statuses: list[ExecutionStatus],
        issues: list[RuntimeIssue],
    ) -> ExecutionStatus:
        status = max(statuses or [ExecutionStatus.READY], key=_STATUS_RANK.__getitem__)
        if status is ExecutionStatus.READY and issues:
            return ExecutionStatus.DEGRADED
        return status

    @staticmethod
    def _merge_artifacts(
        current: dict[str, ArtifactPointer],
        incoming: Mapping[str, ArtifactPointer],
    ) -> None:
        for name, pointer in incoming.items():
            prior = current.get(name)
            if prior is not None and prior != pointer:
                raise BoundaryValidationError(f"capabilities produced conflicting artifact: {name}")
            current[name] = pointer
