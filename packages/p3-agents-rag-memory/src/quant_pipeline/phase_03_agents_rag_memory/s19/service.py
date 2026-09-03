from __future__ import annotations

from .activation_gate import build_activation_panel
from .forbidden import reject_forbidden_fields
from .heartbeat_scheduler import build_cognitive_cycle_schedule
from .models import (
    ActivationConfig,
    CurrentPersonStatePanelInput,
    HeartbeatConfig,
    PersonSeedPanelInput,
    StimulusPanelInput,
    SubphaseS19Result,
    ValidatedPopulationManifestInput,
)


def run_s19(inputs: dict, config: dict) -> SubphaseS19Result:
    """Run both P3.S19 modules with strict input and config validation."""

    reject_forbidden_fields(inputs)
    reject_forbidden_fields(config)
    stimulus_panel = StimulusPanelInput.model_validate(inputs["stimulus_panel"])
    state_panel = CurrentPersonStatePanelInput.model_validate(
        inputs["current_person_state_panel"]
    )
    seed_panel = PersonSeedPanelInput.model_validate(inputs["person_seed_panel"])
    population = ValidatedPopulationManifestInput.model_validate(
        inputs["validated_population_manifest"]
    )
    activation_config = ActivationConfig.model_validate(config["activation_config"])
    heartbeat_config = HeartbeatConfig.model_validate(config["heartbeat_config"])
    activation_panel = build_activation_panel(
        stimulus_panel,
        state_panel,
        seed_panel,
        activation_config,
    )
    schedule = build_cognitive_cycle_schedule(
        activation_panel,
        state_panel,
        population,
        heartbeat_config,
    )
    return SubphaseS19Result(
        activation_panel=activation_panel,
        cognitive_cycle_schedule=schedule,
    )
