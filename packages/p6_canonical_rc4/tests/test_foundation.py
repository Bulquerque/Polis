from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from conftest import DECISION_TIME
from quant_pipeline.phase_06_strategy_synthesis.domain.enums import CapabilityStatus
from quant_pipeline.phase_06_strategy_synthesis.domain.models import BeliefScenario, CapabilityRecord, MarketBeliefState
from quant_pipeline.phase_06_strategy_synthesis.foundation.artifacts import ArtifactStatus, build_artifact


def test_artifact_content_addressed_and_deterministic():
    records=(CapabilityRecord(capability="X",status=CapabilityStatus.AVAILABLE,reason_code="OK",planned_wave=1),)
    kwargs=dict(artifact_type="x",producer_module_id="P6.TEST",run_id="run",cycle_id="cycle",decision_time=DECISION_TIME,created_at=DECISION_TIME+timedelta(seconds=1),available_at=DECISION_TIME+timedelta(seconds=1),records=records)
    assert build_artifact(**kwargs).artifact_id == build_artifact(**kwargs).artifact_id


def test_empty_valid_rejects_records():
    record=CapabilityRecord(capability="X",status=CapabilityStatus.AVAILABLE,reason_code="OK",planned_wave=1)
    with pytest.raises(ValidationError):
        build_artifact(artifact_type="x",producer_module_id="P6.TEST",run_id="run",cycle_id="cycle",decision_time=DECISION_TIME,created_at=DECISION_TIME,available_at=DECISION_TIME,records=(record,),status=ArtifactStatus.EMPTY_VALID)


def test_probability_mass_must_equal_one():
    with pytest.raises(ValidationError):
        MarketBeliefState(belief_state_id="b",underlying_id="X",decision_time=DECISION_TIME,horizon_days=1,scenarios=(BeliefScenario(scenario_id="s",terminal_underlying_price=Decimal("100"),probability=Decimal("0.9")),),confidence=Decimal("1"),regime_context="N",source_artifact_id="a")


def test_limited_belief_cannot_contain_synthetic_scenarios():
    with pytest.raises(ValidationError):
        MarketBeliefState(belief_state_id="b",underlying_id="X",decision_time=DECISION_TIME,horizon_days=1,scenarios=(BeliefScenario(scenario_id="s",terminal_underlying_price=Decimal("100"),probability=Decimal("1")),),confidence=Decimal("1"),regime_context="N",scenario_capability=CapabilityStatus.LIMITED,source_artifact_id="a")
