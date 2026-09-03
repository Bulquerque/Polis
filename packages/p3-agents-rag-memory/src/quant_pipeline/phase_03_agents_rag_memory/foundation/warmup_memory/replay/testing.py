from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BeliefStatePanel,
    CycleKernelRequest,
    CycleKernelResult,
    KernelExecutionStatus,
    MemoryState,
    ModuleTraceEntry,
    PersonStatePanel,
    ReplayState,
    SocialGraphState,
)
from .service import hash_value, stable_id


@dataclass(slots=True)
class DeterministicFakeCycleKernel:
    """Reference kernel for tests only; production must inject the real runtime kernel."""

    contract_version: str = "cycle-kernel.v1"
    degraded_on_sequence: int | None = None
    fail_on_sequence: int | None = None

    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult:
        sequence = request.schedule_item.sequence_number
        if self.fail_on_sequence == sequence:
            return CycleKernelResult(
                request_id=request.request_id,
                status=KernelExecutionStatus.FAILED,
                next_state=request.prior_state,
                module_trace=(),
                issues=({"code": "FAKE_KERNEL_FAILURE"},),
            )
        updated_person_records = tuple(
            record.model_copy(update={
                "attention": min(1.0, record.attention + 0.01),
                "last_updated_at": request.logical_time,
            })
            for record in request.prior_state.person_state.records
        )
        person_panel = PersonStatePanel(records=updated_person_records, content_hash=hash_value(updated_person_records))
        belief_panel = BeliefStatePanel(records=request.prior_state.belief_state.records, content_hash=hash_value(request.prior_state.belief_state.records))
        memory_state = MemoryState(records=request.prior_state.memory_state.records, content_hash=hash_value(request.prior_state.memory_state.records))
        graph = SocialGraphState(records=request.prior_state.social_graph.records, content_hash=hash_value(request.prior_state.social_graph.records))
        payload = request.prior_state.model_dump()
        payload.update({
            "replay_cycle_number": request.prior_state.replay_cycle_number + 1,
            "as_of_time": request.logical_time,
            "person_state": person_panel,
            "belief_state": belief_panel,
            "memory_state": memory_state,
            "social_graph": graph,
            "lineage": request.prior_state.lineage.model_copy(update={"parent_state_hash": request.prior_state.state_hash}),
        })
        payload.pop("state_hash", None)
        next_state = ReplayState(**payload, state_hash=hash_value(payload))
        status = KernelExecutionStatus.DEGRADED if self.degraded_on_sequence == sequence else KernelExecutionStatus.SUCCEEDED
        module_id = "P3.S17.M01" if request.schedule_item.event_ref is not None else "P3.S19.M02"
        trace = ModuleTraceEntry(
            cycle_id=request.cycle_id,
            module_id=module_id,
            input_hashes=(request.prior_state.state_hash,),
            output_hashes=(next_state.state_hash,),
            as_of_time=request.logical_time,
            status=status.value,
        )
        return CycleKernelResult(
            request_id=request.request_id,
            status=status,
            next_state=next_state,
            module_trace=(trace,),
        )
