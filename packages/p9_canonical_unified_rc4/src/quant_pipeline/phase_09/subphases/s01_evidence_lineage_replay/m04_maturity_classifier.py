from __future__ import annotations

from datetime import timedelta

from quant_pipeline.phase_09.contracts.maturity import (
    EvaluationEligibilityPanel,
    LifecycleStatus,
    MaturityBasis,
    MaturityDecision,
    MaturityDecisionTrace,
    MaturityState,
    MaturitySubject,
    MaturitySubjectManifest,
    OutcomeMaturityPanel,
    OutcomeMaturityPolicy,
    OutcomeMaturityPolicyRegistry,
)


class OutcomeMaturityAndCensoringClassifier:
    module_id = "P9.S1.M04"

    def classify(
        self,
        *,
        manifest: MaturitySubjectManifest,
        policy_registry: OutcomeMaturityPolicyRegistry,
        evaluation_as_of,
    ) -> tuple[OutcomeMaturityPanel, EvaluationEligibilityPanel, MaturityDecisionTrace]:
        decisions: list[MaturityDecision] = []
        eligible_keys: list[str] = []
        ineligible_keys: list[str] = []

        for subject in manifest.payload.subjects:
            matching = [
                policy
                for policy in policy_registry.policies
                if policy.target_type == subject.target_type
            ]
            if not matching:
                decision = MaturityDecision(
                    subject_id=subject.subject_id,
                    metric_family="UNREGISTERED",
                    state=MaturityState.UNOBSERVABLE,
                    required_at=None,
                    evaluation_as_of=evaluation_as_of,
                    observable=False,
                    eligible=False,
                    reason_codes=("P9_S1_OUTCOME_POLICY_MISSING",),
                )
                decisions.append(decision)
                ineligible_keys.append(self._key(decision))
                continue
            for policy in matching:
                decision = self._classify_one(subject, policy, evaluation_as_of)
                decisions.append(decision)
                key = self._key(decision)
                if decision.eligible:
                    eligible_keys.append(key)
                else:
                    ineligible_keys.append(key)

        panel = OutcomeMaturityPanel(
            decisions=tuple(
                sorted(decisions, key=lambda item: (item.subject_id, item.metric_family))
            )
        )
        eligibility = EvaluationEligibilityPanel(
            eligible_keys=tuple(sorted(eligible_keys)),
            ineligible_keys=tuple(sorted(ineligible_keys)),
        )
        trace = MaturityDecisionTrace(
            evaluation_as_of=evaluation_as_of,
            policy_ids=tuple(sorted(policy.policy_id for policy in policy_registry.policies)),
            decision_count=len(decisions),
        )
        return panel, eligibility, trace

    @staticmethod
    def _key(decision: MaturityDecision) -> str:
        return f"{decision.subject_id}::{decision.metric_family}"

    def _classify_one(
        self,
        subject: MaturitySubject,
        policy: OutcomeMaturityPolicy,
        evaluation_as_of,
    ) -> MaturityDecision:
        required_at = self._required_at(subject, policy)
        if (
            subject.censoring_reason is not None
            or subject.lifecycle_status is LifecycleStatus.DELISTED
        ):
            return MaturityDecision(
                subject_id=subject.subject_id,
                metric_family=policy.metric_family,
                state=MaturityState.CENSORED,
                required_at=required_at,
                evaluation_as_of=evaluation_as_of,
                observable=False,
                eligible=False,
                reason_codes=("P9_S1_OUTCOME_CENSORED",),
            )
        if required_at is None:
            return MaturityDecision(
                subject_id=subject.subject_id,
                metric_family=policy.metric_family,
                state=MaturityState.UNOBSERVABLE,
                required_at=None,
                evaluation_as_of=evaluation_as_of,
                observable=False,
                eligible=False,
                reason_codes=("P9_S1_OUTCOME_LIFECYCLE_UNRESOLVED",),
            )
        required_at = required_at + timedelta(seconds=policy.grace_period_seconds)
        observable = (
            subject.data_available_at is not None and subject.data_available_at <= evaluation_as_of
        )
        if evaluation_as_of < required_at:
            partial = (
                policy.allow_partial
                and subject.observation_end is not None
                and subject.observation_end > subject.decision_time
                and subject.observation_end <= evaluation_as_of
            )
            state = MaturityState.PARTIALLY_MATURED if partial else MaturityState.NOT_MATURED
            return MaturityDecision(
                subject_id=subject.subject_id,
                metric_family=policy.metric_family,
                state=state,
                required_at=required_at,
                evaluation_as_of=evaluation_as_of,
                observable=observable,
                eligible=partial and (observable or not policy.requires_observable_data),
                reason_codes=(
                    "P9_S1_OUTCOME_PARTIAL" if partial else "P9_S1_OUTCOME_NOT_MATURED",
                ),
            )
        settled = subject.lifecycle_status is LifecycleStatus.SETTLED
        state = MaturityState.SETTLED if settled else MaturityState.MATURED
        eligible = observable or not policy.requires_observable_data
        return MaturityDecision(
            subject_id=subject.subject_id,
            metric_family=policy.metric_family,
            state=state,
            required_at=required_at,
            evaluation_as_of=evaluation_as_of,
            observable=observable,
            eligible=eligible,
            reason_codes=() if eligible else ("P9_S1_OUTCOME_DATA_UNAVAILABLE",),
        )

    @staticmethod
    def _required_at(subject: MaturitySubject, policy: OutcomeMaturityPolicy):
        if policy.basis is MaturityBasis.HORIZON:
            return subject.horizon_end
        if policy.basis is MaturityBasis.CLOSE:
            return subject.close_time
        if policy.basis is MaturityBasis.EXPIRATION:
            return subject.expiration_time
        if policy.basis is MaturityBasis.SETTLEMENT:
            return subject.settlement_time
        return None
