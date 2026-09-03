from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import ExternalStimulusStream, ResolvedExternalStimulusStream
from .stimulus_builder import build_external_stimulus_stream
from .underlying_resolver import resolve_external_stimulus_stream


class SubphaseS17Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    external_stimulus_stream: ExternalStimulusStream
    resolved_external_stimulus_stream: ResolvedExternalStimulusStream


def run_subphase(inputs: dict[str, object]) -> SubphaseS17Result:
    """Run P3.S17.M01 and P3.S17.M02 in canonical order."""

    external = build_external_stimulus_stream(inputs)
    resolved = resolve_external_stimulus_stream(
        {
            "external_stimulus_stream": external.model_dump(mode="python"),
            "entity_underlying_map_config": inputs["entity_underlying_map_config"],
            "proposition_registry_config": inputs["proposition_registry_config"],
        }
    )
    return SubphaseS17Result(
        external_stimulus_stream=external,
        resolved_external_stimulus_stream=resolved,
    )
