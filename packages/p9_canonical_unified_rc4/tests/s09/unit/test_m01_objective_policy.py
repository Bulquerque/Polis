from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    CompetitionObjectiveSpec,
    build_competition_objective_policy,
)

from tests.s09.conftest import objective_spec


def test_compiles_policy_deterministically() -> None:
    result = build_competition_objective_policy(objective_spec())
    assert result.status.value == "SUCCESS"
    assert result.output is not None
    assert result.output.primary_score_id == "competition_score"
    assert result.output_sha256 is not None
    second = build_competition_objective_policy(objective_spec())
    assert result.output_sha256 == second.output_sha256


def test_rejects_policy_committed_after_evaluation() -> None:
    spec = objective_spec()
    payload = spec.model_dump()
    payload["committed_at"] = spec.evaluation_started_at + timedelta(seconds=1)
    with pytest.raises(ValidationError):
        CompetitionObjectiveSpec.model_validate(payload)
