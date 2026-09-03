"""P6.S2 module implementations."""

from __future__ import annotations

from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult
from .services import (
    constraint_registry,
    contract_existence_gate,
    identity_policy,
    objective_registry,
    template_registry,
)


def _artifact(records, artifact_type, module_id, context, input_ids=(), status=None):
    return build_artifact(
        artifact_type=artifact_type,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=records,
        input_artifact_ids=input_ids,
        status=status,
    )


def existence(inputs, context, configuration):
    module_id="P6.S2.M01"
    contracts, quotes, rejected = contract_existence_gate(
        inputs["validated_option_contract_panel"].records,
        inputs["arbitrage_validated_option_quote_panel"].records,
        configuration,
    )
    contract_artifact=_artifact(contracts,"eligible_option_contract_panel",module_id,context)
    quote_artifact=_artifact(quotes,"eligible_option_quote_panel",module_id,context)
    rejection_artifact=_artifact(
        rejected,"contract_rejection_report",module_id,context,
        status=ArtifactStatus.COMPLETE if rejected else ArtifactStatus.EMPTY_VALID,
    )
    return ModuleResult(module_id=module_id,outputs={
        "eligible_option_contract_panel":contract_artifact,
        "eligible_option_quote_panel":quote_artifact,
        "contract_rejection_report":rejection_artifact,
    })


def grammar(inputs, context, configuration):
    module_id="P6.S2.M02"
    artifact=_artifact(template_registry(),"strategy_template_registry",module_id,context)
    return ModuleResult(module_id=module_id,outputs={"strategy_template_registry":artifact})


def objectives(inputs, context, configuration):
    module_id="P6.S2.M03"
    artifact=_artifact(objective_registry(),"objective_family_registry",module_id,context)
    return ModuleResult(module_id=module_id,outputs={"objective_family_registry":artifact})


def constraints(inputs, context, configuration):
    module_id="P6.S2.M04"
    artifact=_artifact(constraint_registry(configuration),"constraint_policy_registry",module_id,context)
    return ModuleResult(module_id=module_id,outputs={"constraint_policy_registry":artifact})


def identity(inputs, context, configuration):
    module_id="P6.S2.M05"
    artifact=_artifact(identity_policy(configuration),"strategy_identity_policy",module_id,context)
    return ModuleResult(module_id=module_id,outputs={"strategy_identity_policy":artifact})
