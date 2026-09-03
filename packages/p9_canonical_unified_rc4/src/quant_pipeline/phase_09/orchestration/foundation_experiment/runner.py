from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quant_pipeline.phase_09.contracts.cohort import (
    CohortPolicyRegistry,
    HoldoutAccessLedger,
    ResearchCommitmentRegistry,
)
from quant_pipeline.phase_09.contracts.handoff import P8EvaluationHandoffV1
from quant_pipeline.phase_09.contracts.maturity import OutcomeMaturityPolicyRegistry
from quant_pipeline.phase_09.contracts.replay import ReplayPolicy
from quant_pipeline.phase_09.contracts.s1 import S1ExecutionOutputs
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m02_lineage_resolver import (
    LineageResolutionPolicy,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.runner import S1Runner
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.request import S2RunRequest
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.trials import FoundationExecutionResult
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import S2Runner


@dataclass(frozen=True, slots=True)
class S1RunCommand:
    handoff: P8EvaluationHandoffV1
    lineage_policy: LineageResolutionPolicy
    replay_policy: ReplayPolicy
    maturity_policies: OutcomeMaturityPolicyRegistry
    commitments: ResearchCommitmentRegistry
    cohort_policies: CohortPolicyRegistry
    holdout_access: HoldoutAccessLedger
    evaluation_as_of: datetime
    metric_family: str = "primary"


@dataclass(frozen=True, slots=True)
class FoundationIntegratedResult:
    s1_outputs: S1ExecutionOutputs
    s2_result: FoundationExecutionResult | None


class FoundationIntegratedRunner:
    """Compose S1 and S2 while preserving their independent authorities."""

    def __init__(self, *, s1_runner: S1Runner, s2_runner: S2Runner) -> None:
        self._s1_runner = s1_runner
        self._s2_runner = s2_runner

    def run(
        self,
        *,
        s1_command: S1RunCommand,
        s2_request_template: S2RunRequest,
    ) -> FoundationIntegratedResult:
        s1_outputs = self._s1_runner.run(
            handoff=s1_command.handoff,
            lineage_policy=s1_command.lineage_policy,
            replay_policy=s1_command.replay_policy,
            maturity_policies=s1_command.maturity_policies,
            commitments=s1_command.commitments,
            cohort_policies=s1_command.cohort_policies,
            holdout_access=s1_command.holdout_access,
            evaluation_as_of=s1_command.evaluation_as_of,
            metric_family=s1_command.metric_family,
        )
        if s1_outputs.subphase_receipt.payload.status.value != "SUCCESS":
            return FoundationIntegratedResult(s1_outputs=s1_outputs, s2_result=None)

        raw = s2_request_template.model_dump(mode="python")
        raw["s1_outputs"] = s1_outputs
        s2_request = S2RunRequest.model_validate(raw)
        return FoundationIntegratedResult(
            s1_outputs=s1_outputs,
            s2_result=self._s2_runner.run(s2_request),
        )
