from __future__ import annotations

import json
from pathlib import Path

from .input_models import S7ToS8Handoff, S8InputBundle, S8PolicyBundle
from .management_models import ManagementDecisionBundle, ReoptimizationRequest
from .prior_state_models import PriorPortfolioState
from .state_models import AccountingBundle, ExecutionStateBundle, PositionLifecycleBundle, StatefulEvidenceBundle
from .timeline_models import OrderedEventQueue
from .valuation_models import MarkSnapshot, ValuationBundle

MODELS={
 "s7_to_s8_handoff":S7ToS8Handoff,"s8_input_bundle":S8InputBundle,"s8_policy_bundle":S8PolicyBundle,
 "prior_portfolio_state":PriorPortfolioState,"ordered_event_queue":OrderedEventQueue,
 "execution_state_bundle":ExecutionStateBundle,"position_lifecycle_bundle":PositionLifecycleBundle,
 "accounting_bundle":AccountingBundle,"mark_snapshot":MarkSnapshot,"valuation_bundle":ValuationBundle,
 "management_decision_bundle":ManagementDecisionBundle,"reoptimization_request":ReoptimizationRequest,
 "stateful_evidence_bundle":StatefulEvidenceBundle,
}


def export(directory:Path)->None:
    directory.mkdir(parents=True,exist_ok=True)
    for name,model in MODELS.items():
        (directory/f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(),indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
