"""Validated entrypoints for P3.S28 modules."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from .common import log_event
from .errors import S28ContractError, S28Error
from .projection import project_tags
from .quality import validate_society_vector
from .types import (
    AttentionInformationMetrics,
    BeliefDistributionPanel,
    CascadeMetricsPanel,
    EmergenceVectorConfig,
    NextBeliefStatePanel,
    PersonSeedPanel,
    PersonalityTagRegistry,
    Phase3RunSnapshot,
    PropositionRegistryConfig,
    S28AggregationSemanticsConfig,
    SourceQualityPanel,
    SyntheticSocietyStatePanel,
    TagProjectionPanel,
    ValidatedNextPersonStatePanel,
    ValidatedPopulationManifest,
)
from .vector import build_society_vector

FORBIDDEN_FIELDS = {
    "future_return", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "buy_sell_signal"
}


def _reject_forbidden(value: object, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in FORBIDDEN_FIELDS:
                raise S28ContractError(f"forbidden field at {path}/{key}")
            _reject_forbidden(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}/{index}")


def _require_inputs(inputs: Mapping[str, object], required: tuple[str, ...]) -> None:
    missing = [name for name in required if name not in inputs]
    extra = [name for name in inputs if name not in required]
    if missing or extra:
        raise S28ContractError(f"input surface mismatch; missing={missing}, extra={extra}")
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
    except (ValidationError, S28Error, ValueError, TypeError) as exc:
        log_event("module_failed", module_id=module_id, run_id=run_id, cycle_id=cycle_id, status="FAILED", error_type=type(exc).__name__)
        raise
    log_event("module_succeeded", module_id=module_id, run_id=run_id, cycle_id=cycle_id, status="READY", output_count=len(output))
    return output


def run_m01(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    required = (
        "next_belief_state_panel", "person_seed_panel", "validated_population_manifest",
        "validated_next_person_state_panel", "personality_tag_registry",
        "proposition_registry_config", "aggregation_semantics_config",
    )
    _require_inputs(inputs, required)

    def operation() -> dict[str, object]:
        panel = project_tags(
            next_belief_state_panel=NextBeliefStatePanel.model_validate(inputs["next_belief_state_panel"]),
            person_seed_panel=PersonSeedPanel.model_validate(inputs["person_seed_panel"]),
            validated_population_manifest=ValidatedPopulationManifest.model_validate(inputs["validated_population_manifest"]),
            validated_next_person_state_panel=ValidatedNextPersonStatePanel.model_validate(inputs["validated_next_person_state_panel"]),
            personality_tag_registry=PersonalityTagRegistry.model_validate(inputs["personality_tag_registry"]),
            proposition_registry_config=_config(config, inputs, "proposition_registry_config", PropositionRegistryConfig),
            aggregation_semantics_config=_config(config, inputs, "aggregation_semantics_config", S28AggregationSemanticsConfig),
        )
        return {"tag_projection_panel": panel.model_dump(mode="json")}

    return _run("P3.S28.M01", operation, inputs)


def run_m02(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    required = (
        "belief_distribution_panel", "attention_information_metrics", "cascade_metrics_panel",
        "tag_projection_panel", "emergence_vector_config", "aggregation_semantics_config",
    )
    _require_inputs(inputs, required)

    def operation() -> dict[str, object]:
        panel = build_society_vector(
            belief_distribution_panel=BeliefDistributionPanel.model_validate(inputs["belief_distribution_panel"]),
            attention_information_metrics=AttentionInformationMetrics.model_validate(inputs["attention_information_metrics"]),
            cascade_metrics_panel=CascadeMetricsPanel.model_validate(inputs["cascade_metrics_panel"]),
            tag_projection_panel=TagProjectionPanel.model_validate(inputs["tag_projection_panel"]),
            emergence_vector_config=_config(config, inputs, "emergence_vector_config", EmergenceVectorConfig),
            aggregation_semantics_config=_config(config, inputs, "aggregation_semantics_config", S28AggregationSemanticsConfig),
        )
        return {"synthetic_society_state_panel": panel.model_dump(mode="json")}

    return _run("P3.S28.M02", operation, inputs)


def run_m03(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    required = ("synthetic_society_state_panel", "source_quality_panel", "phase3_run_snapshot", "emergence_vector_config")
    _require_inputs(inputs, required)

    def operation() -> dict[str, object]:
        panel = validate_society_vector(
            synthetic_society_state_panel=SyntheticSocietyStatePanel.model_validate(inputs["synthetic_society_state_panel"]),
            source_quality_panel=SourceQualityPanel.model_validate(inputs["source_quality_panel"]),
            phase3_run_snapshot=Phase3RunSnapshot.model_validate(inputs["phase3_run_snapshot"]),
            emergence_vector_config=_config(config, inputs, "emergence_vector_config", EmergenceVectorConfig),
        )
        return {"validated_society_state_panel": panel.model_dump(mode="json")}

    return _run("P3.S28.M03", operation, inputs)
