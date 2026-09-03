from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from ..runtime.resources import resource_root
from ..runtime.yaml_loader import load_yaml


@dataclass(frozen=True, slots=True)
class ArtifactPolicy:
    artifact_name: str
    modality: str
    entity_type: str
    identity_fields: tuple[str, ...]
    reference_fields: tuple[str, ...]
    event_fields: tuple[str, ...]
    published_fields: tuple[str, ...]
    available_fields: tuple[str, ...]
    ingested_fields: tuple[str, ...]
    timezone_fields: tuple[str, ...]
    revision_key_fields: tuple[str, ...]
    dimension_fields: tuple[str, ...]
    required_value_fields: tuple[str, ...]
    optional_value_fields: tuple[str, ...]
    allow_created_at_availability_fallback: bool
    default_timezone: str
    date_only_reference_policy: str
    date_only_event_policy: str
    date_only_available_policy: str

    @classmethod
    def from_mapping(
        cls,
        artifact_name: str,
        value: Mapping[str, Any],
        defaults: Mapping[str, Any],
    ) -> "ArtifactPolicy":
        def values(name: str) -> tuple[str, ...]:
            raw = value.get(name, ())
            return tuple(str(item) for item in raw) if isinstance(raw, list) else ()

        return cls(
            artifact_name=artifact_name,
            modality=str(value.get("modality", "UNCLASSIFIED")),
            entity_type=str(value.get("entity_type", "UNCLASSIFIED")),
            identity_fields=values("identity_fields"),
            reference_fields=values("reference_fields"),
            event_fields=values("event_fields"),
            published_fields=values("published_fields"),
            available_fields=values("available_fields"),
            ingested_fields=values("ingested_fields"),
            timezone_fields=values("timezone_fields") or ("timezone", "source_timezone"),
            revision_key_fields=values("revision_key_fields"),
            dimension_fields=values("dimension_fields"),
            required_value_fields=values("required_value_fields"),
            optional_value_fields=values("optional_value_fields"),
            allow_created_at_availability_fallback=bool(
                value.get("allow_created_at_availability_fallback", False)
            ),
            default_timezone=str(value.get("timezone", defaults.get("timezone", "UTC"))),
            date_only_reference_policy=str(
                value.get(
                    "date_only_reference_policy",
                    defaults.get("date_only_reference_policy", "start_of_day"),
                )
            ),
            date_only_event_policy=str(
                value.get(
                    "date_only_event_policy",
                    defaults.get("date_only_event_policy", "start_of_day"),
                )
            ),
            date_only_available_policy=str(
                value.get(
                    "date_only_available_policy",
                    defaults.get("date_only_available_policy", "end_of_day"),
                )
            ),
        )


@lru_cache(maxsize=1)
def artifact_policies() -> dict[str, ArtifactPolicy]:
    path = resource_root().joinpath("registries", "artifact_semantics.yaml")
    raw = load_yaml(path)
    defaults = raw.get("defaults", {})
    artifacts = raw.get("artifacts", {})
    return {
        str(name): ArtifactPolicy.from_mapping(str(name), value, defaults)
        for name, value in artifacts.items()
        if isinstance(value, Mapping)
    }


def policy_for(artifact_name: str) -> ArtifactPolicy:
    policies = artifact_policies()
    if artifact_name in policies:
        return policies[artifact_name]
    return ArtifactPolicy.from_mapping(
        artifact_name,
        {
            "modality": "UNCLASSIFIED",
            "entity_type": "UNCLASSIFIED",
            "identity_fields": ["entity_id", "underlying_id", "underlying"],
            "reference_fields": ["reference_time", "date"],
            "event_fields": ["event_time", "timestamp"],
            "published_fields": ["published_at", "publication_time"],
            "available_fields": ["available_at"],
            "ingested_fields": ["ingested_at"],
        },
        {"timezone": "UTC"},
    )
