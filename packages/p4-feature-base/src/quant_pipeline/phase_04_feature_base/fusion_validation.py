from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from pydantic import ValidationError

from .economic_errors import ContractError
from .economic_models import ExecutionContext
from .validation import find_forbidden_fields
from .perspective_models import PerspectiveExecutionRegistry, PerspectiveFeaturePanel
from .fusion_models import AlignmentPolicyRegistry, ApprovedInteractionRegistry, ConflictGroupRegistry

PERSPECTIVE_ARTIFACTS=(
    "momentum_perspective_panel","reversion_relative_value_perspective_panel",
    "risk_uncertainty_stress_perspective_panel","liquidity_attention_crowding_perspective_panel",
    "structure_contagion_breadth_perspective_panel","macro_cycle_regime_state_perspective_panel",
    "event_surprise_seasonality_perspective_panel","narrative_evidence_disagreement_perspective_panel",
    "value_quality_profitability_investment_perspective_panel","carry_curve_basis_perspective_panel",
)


def prepare_s6_inputs(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> dict[str,Any]:
    prepared=dict(inputs)
    leaked=find_forbidden_fields(inputs)
    if leaked:
        raise ContractError("P4_S6_FORBIDDEN_FIELD","forbidden fields detected",details={"paths":leaked})
    try:
        context=ExecutionContext.model_validate(config)
        registry=prepared.get("approved_hypothesis_passport_registry")
        if registry is None: raise KeyError("approved_hypothesis_passport_registry")
        prepared["approved_hypothesis_passport_registry"] = registry if isinstance(registry,PerspectiveExecutionRegistry) else PerspectiveExecutionRegistry.model_validate(registry)
        for name in PERSPECTIVE_ARTIFACTS:
            raw=prepared.get(name)
            if raw is not None and not isinstance(raw,PerspectiveFeaturePanel):
                prepared[name]=PerspectiveFeaturePanel.model_validate(raw)
        for name,model in (
            ("alignment_policy_registry",AlignmentPolicyRegistry),
            ("conflict_group_registry",ConflictGroupRegistry),
            ("approved_interaction_registry",ApprovedInteractionRegistry),
        ):
            raw=prepared.get(name)
            if raw is None: raise KeyError(name)
            prepared[name]=raw if isinstance(raw,model) else model.model_validate(raw)
    except KeyError as exc:
        raise ContractError("P4_S6_INPUT_MISSING",f"missing required input: {exc.args[0]}") from exc
    except ValidationError as exc:
        raise ContractError("P4_S6_SCHEMA_INVALID","S6 input validation failed",details={"errors":exc.errors(include_url=False)}) from exc
    authorities=[prepared["approved_hypothesis_passport_registry"],prepared["alignment_policy_registry"],prepared["conflict_group_registry"],prepared["approved_interaction_registry"]]
    panels=[prepared[name] for name in PERSPECTIVE_ARTIFACTS if prepared.get(name) is not None]
    mismatched=[getattr(obj,"artifact_name",getattr(obj,"artifact_id",type(obj).__name__)) for obj in [*authorities,*panels] if obj.run_id!=context.run_id or obj.cycle_id!=context.cycle_id or obj.as_of_time!=context.as_of_time or obj.pipeline_version!=context.pipeline_version]
    if mismatched:
        raise ContractError("P4_S6_CONTEXT_MISMATCH","S6 inputs do not match execution context",details={"artifacts":sorted(mismatched)})
    return prepared
