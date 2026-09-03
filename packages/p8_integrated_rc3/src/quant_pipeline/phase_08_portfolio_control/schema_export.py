from __future__ import annotations

import json
from pathlib import Path

from .contracts.execution_authorization import P8ExecutionAuthorizationBundle
from .foundation.context import ModuleExecutionContext
from .subphases.s07_execution.models import (
    ExecutionReceipt,
    ExecutionResult,
    ExecutionStructureBundle,
    MarketStateSnapshot,
    OrderIntentBundle,
    PlannedOrderBundle,
    PretradeCostBundle,
    RuntimeControlCommand,
    VenueCapabilities,
)
from .subphases.s07_execution.policies import S7PolicyBundle
from .subphases.s08_stateful_engine.schema_export import MODELS as S8_MODELS
from .subphases.s10_audit_release.models_handoff import (
    P9FullEvidenceArtifact,
    P9FullEvidenceBundle,
)

MODELS = {
    "p8_execution_authorization_bundle_v1": P8ExecutionAuthorizationBundle,
    "module_execution_context": ModuleExecutionContext,
    "market_state_snapshot": MarketStateSnapshot,
    "venue_capabilities": VenueCapabilities,
    "s7_policy_bundle": S7PolicyBundle,
    "order_intent_bundle": OrderIntentBundle,
    "execution_structure_bundle": ExecutionStructureBundle,
    "planned_order_bundle": PlannedOrderBundle,
    "pretrade_cost_bundle": PretradeCostBundle,
    "execution_result": ExecutionResult,
    "execution_receipt": ExecutionReceipt,
    "runtime_control_command_v1": RuntimeControlCommand,
    "p9_full_evidence_artifact_v1": P9FullEvidenceArtifact,
    "p9_full_evidence_bundle_v1": P9FullEvidenceBundle,
    **S8_MODELS,
}


def export(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema(mode="validation")
        (directory / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
