from __future__ import annotations

from pydantic import Field

from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256
from quant_pipeline.phase_08_portfolio_control.foundation.models import StrictModel

from . import m01_timeline, m02_execution_state, m03_positions, m04_accounting, m05_valuation, m06_management, m07_checkpoint
from .base_models import payload_hash
from .errors import LedgerIntegrityError
from .input_models import S8InputBundle
from .management_models import ManagementDecisionBundle
from .state_models import AccountingBundle, ExecutionStateBundle, PositionLifecycleBundle, StatefulEvidenceBundle
from .timeline_models import OrderedEventQueue
from .valuation_models import ValuationBundle


class S8Result(StrictModel):
    ordered_events: OrderedEventQueue
    execution_state: ExecutionStateBundle
    positions: PositionLifecycleBundle
    accounting: AccountingBundle
    valuation: ValuationBundle
    management: ManagementDecisionBundle
    evidence: StatefulEvidenceBundle
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _validate_input(value:S8InputBundle)->None:
    if payload_hash(value.s7_handoff)!=value.s7_handoff.content_sha256:
        raise LedgerIntegrityError("S7→S8 handoff hash mismatch")
    if payload_hash(value)!=value.content_sha256:
        raise LedgerIntegrityError("S8 input hash mismatch")


def run(value:S8InputBundle)->S8Result:
    _validate_input(value)
    queue=m01_timeline.execute(value)
    execution=m02_execution_state.execute(value,queue)
    positions=m03_positions.execute(value,queue,execution)
    accounting=m04_accounting.execute(value,queue,positions)
    valuation=m05_valuation.execute(value,positions,accounting)
    management=m06_management.execute(value,execution,positions,accounting,valuation)
    evidence=m07_checkpoint.execute(value,queue,execution,positions,accounting,valuation,management)
    core={"ordered_events":queue,"execution_state":execution,"positions":positions,"accounting":accounting,"valuation":valuation,"management":management,"evidence":evidence}
    return S8Result(**core,content_sha256=content_sha256(core))
