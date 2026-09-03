from __future__ import annotations

from time import perf_counter

from .canonical import compute_artifact_hash
from .entitlement import build_entitlement_panel
from .errors import ErrorCategory, InvariantError, error
from .models import (
    PersonSchemaPolicy,
    PersonSeedPanel,
    PersonToolEntitlementPanel,
    ToolEntitlementConfig,
    ToolRegistryArtifact,
)
from .ports import EventSinkPort


class PersonToolEntitlementRouter:
    MODULE_ID = "P3.S15.M02"

    def __init__(self, *, event_sink: EventSinkPort) -> None:
        self._events = event_sink

    def run(
        self,
        *,
        tool_registry: ToolRegistryArtifact,
        person_seed_panel: PersonSeedPanel,
        person_schema_policy: PersonSchemaPolicy,
        entitlement_config: ToolEntitlementConfig,
    ) -> PersonToolEntitlementPanel:
        started = perf_counter()
        dims = {
            "run_id": tool_registry.run_id,
            "cycle_id": tool_registry.cycle_id,
            "snapshot_id": tool_registry.snapshot_id,
            "module_id": self.MODULE_ID,
            "as_of_time": tool_registry.as_of_time.isoformat(),
        }
        self._events.emit("module_started", dims)
        try:
            if compute_artifact_hash(tool_registry) != tool_registry.content_hash:
                raise InvariantError(
                    error(
                        "P3_S15_M02_TOOL_REGISTRY_HASH_MISMATCH",
                        ErrorCategory.INVARIANT,
                        "tool_registry content_hash is not recomputable",
                    )
                )
            self._events.emit("input_contract_validated", dims)
            panel = build_entitlement_panel(
                registry=tool_registry,
                persons=person_seed_panel,
                person_schema_policy=person_schema_policy,
                config=entitlement_config,
            )
            self._events.emit(
                "module_succeeded",
                {
                    **dims,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "input_record_count": len(person_seed_panel.records),
                    "output_record_count": len(panel.records),
                    "warning_count": len(panel.issues),
                    "error_count": 0,
                },
            )
            return panel
        except Exception:
            self._events.emit(
                "module_failed",
                {
                    **dims,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "input_record_count": len(person_seed_panel.records),
                    "output_record_count": 0,
                    "warning_count": 0,
                    "error_count": 1,
                },
            )
            raise
