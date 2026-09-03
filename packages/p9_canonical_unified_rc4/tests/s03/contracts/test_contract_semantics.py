from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import (
    ArtifactReference,
    Availability,
    ModuleReceipt,
    TerminalStatus,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.execution_models import (
    PhaseName,
    PhaseRunResult,
    RunnerCapability,
)

from tests.s03.conftest import ZERO_HASH, artifact, utc_day


def test_artifact_rejects_non_utc_timezone() -> None:
    with pytest.raises(ValidationError, match="UTC offset"):
        ArtifactReference(
            artifact_id="a",
            artifact_type="x",
            artifact_schema_name="X",
            artifact_schema_version="1.0.0",
            content_sha256=ZERO_HASH,
            producer_module_id="P9.S3.M01",
            run_id="run",
            cycle_id="cycle",
            available_at=utc_day(1).astimezone(timezone(timedelta(hours=3))),
            location="memory://a",
            availability=Availability.AVAILABLE,
        )


def test_artifact_rejects_whitespace_and_extra_fields() -> None:
    base = artifact(artifact_id="a").model_dump(mode="python")
    base["location"] = " "
    with pytest.raises(ValidationError):
        ArtifactReference(**base)
    base = artifact(artifact_id="a").model_dump(mode="python")
    base["unknown"] = "not allowed"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ArtifactReference(**base)


def test_module_receipt_rejects_success_without_output() -> None:
    with pytest.raises(ValidationError, match="requires output_refs"):
        ModuleReceipt(
            module_id="P9.S3.M01",
            status=TerminalStatus.SUCCESS,
            started_at=utc_day(1),
            completed_at=utc_day(2),
            content_sha256=ZERO_HASH,
        )


def test_phase_result_rejects_successful_p8_without_handoff() -> None:
    body = {
        "phase": PhaseName.P8,
        "runner_id": "p8",
        "runner_version": "1.0.0",
        "capability": RunnerCapability.PRODUCTION,
        "status": TerminalStatus.SUCCESS,
        "started_at": utc_day(1),
        "completed_at": utc_day(2),
        "input_artifacts": (),
        "output_artifacts": (artifact(artifact_id="p8-output"),),
        "p8_handoff": None,
    }
    with pytest.raises(ValidationError, match="typed p8_handoff"):
        PhaseRunResult(**body, result_sha256=content_sha256(body))
