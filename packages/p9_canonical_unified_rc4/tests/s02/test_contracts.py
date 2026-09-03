from __future__ import annotations

import json

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import TrialState
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.budget import (
    EarlyStoppingPolicy,
    FidelityLevel,
    SearchBudgetPolicy,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.trials import (
    FoundationExperimentBundle,
    SchedulerPolicy,
    TrialExecutionSlot,
    TrialResourceRequest,
)


def test_contracts_reject_extra_fields(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        type(s2_request).model_validate_json(json.dumps(raw))


def test_fidelity_fraction_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        FidelityLevel(
            fidelity_id="zero",
            ordinal=0,
            resource_fraction=0,
            preserves_transaction_costs=True,
            preserves_lifecycle=True,
            preserves_temporal_order=True,
        )


def test_early_stopping_requires_signal_metrics() -> None:
    with pytest.raises(ValidationError):
        EarlyStoppingPolicy(enabled=True, signal_metric_ids=())


def test_budget_fractions_must_sum_to_one(s2_request) -> None:
    raw = s2_request.budget_policy.model_dump(mode="json")
    raw["exploration_fraction"] = "0.5"
    with pytest.raises(ValidationError):
        SearchBudgetPolicy.model_validate_json(json.dumps(raw))


def test_scheduler_cannot_retry_completed(s2_request) -> None:
    raw = s2_request.scheduler_policy.model_dump(mode="json")
    raw["retryable_terminal_states"] = (TrialState.COMPLETED,)
    with pytest.raises(ValidationError):
        SchedulerPolicy.model_validate_json(json.dumps(raw))


def test_unassigned_trial_requires_adaptive_metadata(result) -> None:
    slot = result.s2_outputs.trial_plan.slots[0]
    raw = slot.model_dump(mode="json")
    raw["configuration_id"] = None
    raw["initial_state"] = TrialState.RESERVED
    with pytest.raises(ValidationError):
        TrialExecutionSlot.model_validate_json(json.dumps(raw))


def test_assigned_trial_cannot_start_reserved(result) -> None:
    slot = result.s2_outputs.trial_plan.slots[0]
    raw = slot.model_dump(mode="json")
    raw["initial_state"] = TrialState.RESERVED
    with pytest.raises(ValidationError):
        TrialExecutionSlot.model_validate_json(json.dumps(raw))


def test_bundle_integrity_is_verified(result) -> None:
    bundle = result.foundation_bundle
    assert bundle is not None
    raw = bundle.model_dump(mode="json")
    raw["integrity"] = IntegrityEnvelope(payload_sha256="0" * 64).model_dump(mode="json")
    with pytest.raises(ValidationError):
        FoundationExperimentBundle.model_validate_json(json.dumps(raw))
