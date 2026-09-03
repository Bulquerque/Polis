"""Isolated adapter for legacy P5-P8 ``run_phase(dict, dict)`` APIs.

The RC4.1 packages expose this dictionary API. The adapter is explicitly
research-only and cannot make a legacy P8 result production-qualifiable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from ..common import ArtifactReference, Availability, TerminalStatus, content_sha256
from ..execution_models import (
    PhaseName,
    PhaseRunRequest,
    PhaseRunResult,
    RunnerCapability,
    finalize_phase_run_result,
)

LegacyRunPhase = Callable[[dict[str, object], dict[str, object]], dict[str, object]]


class LegacyRunPhaseAdapter:
    def __init__(
        self,
        phase: PhaseName,
        run_phase: LegacyRunPhase,
        *,
        runner_version: str = "4.1.0-legacy",
    ) -> None:
        self.phase = phase
        self._run_phase = run_phase
        self._runner_version = runner_version

    @property
    def runner_id(self) -> str:
        return f"legacy:{self.phase.value}:run_phase"

    @property
    def capability(self) -> RunnerCapability:
        return RunnerCapability.LEGACY_RESEARCH_ONLY

    def run(self, request: PhaseRunRequest) -> PhaseRunResult:
        started = datetime.now(UTC)
        payload = {
            "run_id": request.run_id,
            "cycle_id": request.cycle_id,
            "trial_id": request.trial_id,
            "fold_id": request.fold_id,
            "configuration_id": request.configuration_id,
            "input_artifacts": [item.model_dump(mode="json") for item in request.input_artifacts],
        }
        config = {"seed": request.seed, "configuration_sha256": request.configuration_sha256}
        raw = self._run_phase(payload, config)
        completed = datetime.now(UTC)
        digest = content_sha256(raw)
        artifact = ArtifactReference(
            artifact_id=f"legacy:{request.trial_id}:{self.phase.value}",
            artifact_type=f"LEGACY_{self.phase.value}_OUTPUT",
            artifact_schema_name=f"legacy_{self.phase.value.lower()}_dict",
            artifact_schema_version="1.0.0",
            content_sha256=digest,
            producer_module_id=f"EXTERNAL.{self.phase.value}.LEGACY_RUNNER",
            run_id=request.run_id,
            cycle_id=request.cycle_id,
            available_at=completed,
            location=f"memory://legacy/{request.trial_id}/{self.phase.value}",
            availability=Availability.LEGACY_RESEARCH_ONLY,
            record_count=len(raw),
        )
        body = {
            "phase": self.phase,
            "runner_id": self.runner_id,
            "runner_version": self._runner_version,
            "capability": self.capability,
            "status": (
                TerminalStatus.CAPABILITY_UNAVAILABLE
                if self.phase is PhaseName.P8
                else TerminalStatus.SUCCESS
            ),
            "started_at": started,
            "completed_at": completed,
            "input_artifacts": request.input_artifacts,
            "output_artifacts": (artifact,),
            "reason_codes": (
                "P9_S3_LEGACY_P8_NOT_QUALIFIABLE"
                if self.phase is PhaseName.P8
                else "P9_S3_LEGACY_ADAPTER_USED",
            ),
        }
        return finalize_phase_run_result(
            PhaseRunResult(**body, result_sha256="0" * 64)
        )
