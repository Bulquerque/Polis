from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256, deterministic_id

from .enums import EvidenceStatus, ValuationStatus
from .input_models import S8InputBundle
from .state_models import (
    AccountingBundle,
    ExecutionStateBundle,
    PortfolioStateCheckpoint,
    PositionLifecycleBundle,
    ReplayManifest,
    StatefulEvidenceBundle,
)
from .management_models import ManagementDecisionBundle
from .timeline_models import OrderedEventQueue
from .valuation_models import ValuationBundle
from .version import __version__

MODULE_ID = "P8.S8.M07"


def execute(
    value:S8InputBundle,
    queue:OrderedEventQueue,
    execution:ExecutionStateBundle,
    positions:PositionLifecycleBundle,
    accounting:AccountingBundle,
    valuation:ValuationBundle,
    management:ManagementDecisionBundle,
)->StatefulEvidenceBundle:
    state_payload={"execution":execution,"positions":positions,"accounting":accounting,"valuation":valuation,"management":management}
    state_hash=content_sha256(state_payload)
    policy_hash=content_sha256(value.policies)
    offsets={
        "ordered_events":len(queue.events),"order_events":len(execution.order_events),"fills":len(execution.fills),
        "position_transitions":len(positions.transitions),"journal_entries":len(accounting.journal_entries),
    }
    checkpoint=PortfolioStateCheckpoint(
        checkpoint_id=deterministic_id("checkpoint",value.run_id,value.cycle_id,state_hash),
        as_of_time=value.valuation_time,cycle_id=value.cycle_id,state_content_hash=state_hash,
        ordered_event_hash=queue.content_sha256,policy_hash=policy_hash,module_version=__version__,event_offsets=offsets,
    )
    replay=ReplayManifest(
        replay_id=deterministic_id("replay",value.bundle_id,state_hash),input_hash=value.content_sha256,
        policy_hash=policy_hash,ordered_event_hash=queue.content_sha256,expected_state_hash=state_hash,module_version=__version__,
    )
    no_action=not execution.order_events and not execution.fills and not positions.transitions
    status=EvidenceStatus.NO_ACTION_VALID if no_action else EvidenceStatus.DEGRADED if valuation.nav.status==ValuationStatus.INCOMPLETE else EvidenceStatus.PASS
    core={"bundle_id":deterministic_id("stateful-evidence",value.run_id,value.cycle_id,state_hash),"status":status,"execution_state":execution,"positions":positions,"accounting":accounting,"valuation":valuation,"management":management,"checkpoint":checkpoint,"replay_manifest":replay}
    return StatefulEvidenceBundle(**core,content_sha256=content_sha256(core))
