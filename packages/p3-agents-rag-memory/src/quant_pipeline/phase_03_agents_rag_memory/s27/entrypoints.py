"""Validated entrypoints for the three P3.S27 modules."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from .attention import measure_attention_information
from .beliefs import aggregate_beliefs
from .cascades import measure_cascades
from .common import log_event
from .errors import S27ContractError, S27Error
from .types import (
    ActivationPanel,
    AggregationSemanticsConfig,
    NextBeliefStatePanel,
    PersonToolEntitlementPanel,
    PropositionRegistryConfig,
    SocialDeliveryPanel,
    SocialToolAuditPanel,
    StimulusPanel,
    ToolCallAuditPanel,
    ValidatedNextPersonStatePanel,
    ValidatedPopulationManifest,
)

FORBIDDEN_FIELDS = {"future_return", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "buy_sell_signal"}


def _reject_forbidden(value: object, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in FORBIDDEN_FIELDS:
                raise S27ContractError(f"forbidden field at {path}/{key}")
            _reject_forbidden(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}/{index}")


def _require_inputs(inputs: Mapping[str, object], required: tuple[str, ...]) -> None:
    missing = [name for name in required if name not in inputs]
    extra = [name for name in inputs if name not in required]
    if missing or extra:
        raise S27ContractError(f"input surface mismatch; missing={missing}, extra={extra}")
    _reject_forbidden(inputs)


def _config(config: Mapping[str, object] | None, inputs: Mapping[str, object], key: str, model: type[Any]) -> Any:
    raw = None
    if config is not None:
        raw = config.get(key, config)
    if raw is None:
        raw = inputs[key]
    return model.model_validate(raw)


def _run(module_id: str, operation: Callable[[], dict[str, object]], inputs: Mapping[str, object]) -> dict[str, object]:
    run_id = next((str(value.get("run_id")) for value in inputs.values() if isinstance(value, Mapping) and value.get("run_id")), None)
    cycle_id = next((int(value.get("cycle_id")) for value in inputs.values() if isinstance(value, Mapping) and value.get("cycle_id") is not None), None)
    log_event("module_started", module_id=module_id, run_id=run_id, cycle_id=cycle_id)
    try:
        output = operation()
    except (ValidationError, S27Error, ValueError, TypeError) as exc:
        log_event("module_failed", module_id=module_id, run_id=run_id, cycle_id=cycle_id, status="FAILED", error_type=type(exc).__name__)
        raise
    log_event("module_succeeded", module_id=module_id, run_id=run_id, cycle_id=cycle_id, status="READY", output_count=len(output))
    return output


def run_m01(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    required = ("next_belief_state_panel", "validated_population_manifest", "stimulus_panel", "proposition_registry_config", "aggregation_semantics_config")
    _require_inputs(inputs, required)
    def operation() -> dict[str, object]:
        panel = aggregate_beliefs(
            next_belief_state_panel=NextBeliefStatePanel.model_validate(inputs["next_belief_state_panel"]),
            validated_population_manifest=ValidatedPopulationManifest.model_validate(inputs["validated_population_manifest"]),
            stimulus_panel=StimulusPanel.model_validate(inputs["stimulus_panel"]),
            proposition_registry_config=_config(config, inputs, "proposition_registry_config", PropositionRegistryConfig),
            aggregation_semantics_config=_config(config, inputs, "aggregation_semantics_config", AggregationSemanticsConfig),
        )
        return {"belief_distribution_panel": panel.model_dump(mode="json")}
    return _run("P3.S27.M01", operation, inputs)


def run_m02(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    required = ("validated_next_person_state_panel", "tool_call_audit_panel", "person_tool_entitlement_panel", "validated_population_manifest", "aggregation_semantics_config")
    _require_inputs(inputs, required)
    def operation() -> dict[str, object]:
        panel = measure_attention_information(
            validated_next_person_state_panel=ValidatedNextPersonStatePanel.model_validate(inputs["validated_next_person_state_panel"]),
            tool_call_audit_panel=ToolCallAuditPanel.model_validate(inputs["tool_call_audit_panel"]),
            person_tool_entitlement_panel=PersonToolEntitlementPanel.model_validate(inputs["person_tool_entitlement_panel"]),
            validated_population_manifest=ValidatedPopulationManifest.model_validate(inputs["validated_population_manifest"]),
            aggregation_semantics_config=_config(config, inputs, "aggregation_semantics_config", AggregationSemanticsConfig),
        )
        return {"attention_information_metrics": panel.model_dump(mode="json")}
    return _run("P3.S27.M02", operation, inputs)


def run_m03(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    required = ("activation_panel", "stimulus_panel", "social_delivery_panel", "social_tool_audit_panel", "aggregation_semantics_config")
    _require_inputs(inputs, required)
    def operation() -> dict[str, object]:
        panel = measure_cascades(
            activation_panel=ActivationPanel.model_validate(inputs["activation_panel"]),
            stimulus_panel=StimulusPanel.model_validate(inputs["stimulus_panel"]),
            social_delivery_panel=SocialDeliveryPanel.model_validate(inputs["social_delivery_panel"]),
            social_tool_audit_panel=SocialToolAuditPanel.model_validate(inputs["social_tool_audit_panel"]),
            aggregation_semantics_config=_config(config, inputs, "aggregation_semantics_config", AggregationSemanticsConfig),
        )
        return {"cascade_metrics_panel": panel.model_dump(mode="json")}
    return _run("P3.S27.M03", operation, inputs)
