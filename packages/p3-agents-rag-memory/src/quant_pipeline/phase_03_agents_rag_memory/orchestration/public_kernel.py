"""Public Contract Pack V2 facade over the internal cycle engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from pydantic import JsonValue

from ..contracts import CycleKernelRequest, CycleKernelResult
from ..runtime_engine.contracts_internal import ArtifactPointer as RuntimePointer
from ..runtime_engine.kernel import CycleKernel as InternalCycleKernel
from .boundary import FoundationBundle, adapt_runtime_result, to_runtime_request


class RuntimeJsonRepositoryPort(Protocol):
    """Read immutable JSON artifacts produced by runtime capabilities."""

    async def read_json(self, pointer: RuntimePointer) -> Mapping[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class PublicCycleKernel:
    """Execute the internal engine through the canonical public contracts.

    Executed cycles require the same repository used by runtime capabilities.
    The facade mirrors next-state payloads into the canonical boundary store
    before publishing ReplayState, so S11 can restore N+1 without guessing or
    synthesizing state.
    """

    kernel: InternalCycleKernel
    foundation_bundle: FoundationBundle
    runtime_repository: RuntimeJsonRepositoryPort | None = None

    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult:
        internal_request = to_runtime_request(request, self.foundation_bundle)
        internal_result = await self.kernel.execute_cycle(internal_request)
        public_result, public_closure = adapt_runtime_result(
            request=request,
            result=internal_result,
            bundle=self.foundation_bundle,
        )
        if public_closure is not None:
            if self.runtime_repository is None:
                raise ValueError(
                    "executed public cycles require the runtime artifact repository "
                    "to persist state payloads for ReplayState"
                )
            internal_closure = internal_result.closure_manifest
            if internal_closure is None:  # defensive: public_closure implies internal closure
                raise ValueError("runtime closure disappeared during public adaptation")
            pairs = (
                (internal_closure.next_person_state, public_closure.next_person_state_ref),
                (internal_closure.next_belief_state, public_closure.next_belief_state_ref),
                (internal_closure.next_memory_state, public_closure.next_memory_state_ref),
                (internal_closure.next_social_graph, public_closure.next_social_graph_ref),
                (
                    internal_closure.next_cycle_stimulus_queue,
                    public_closure.next_endogenous_queue_ref,
                ),
                (
                    internal_closure.belief_commitment_log,
                    public_closure.belief_commitments_ref,
                ),
                (internal_closure.tool_audit, public_closure.tool_audit_ref),
                (internal_closure.cycle_audit, public_closure.cycle_snapshot_ref),
            )
            for internal_pointer, public_pointer in pairs:
                payload = await self.runtime_repository.read_json(internal_pointer)
                self.foundation_bundle.public_store.put(public_pointer, payload)
        return public_result
