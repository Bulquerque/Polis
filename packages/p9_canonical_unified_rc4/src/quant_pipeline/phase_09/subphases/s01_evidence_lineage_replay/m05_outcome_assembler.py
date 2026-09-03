from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from quant_pipeline.phase_09.contracts.base import EvidenceClass
from quant_pipeline.phase_09.contracts.integrity import payload_sha256
from quant_pipeline.phase_09.contracts.maturity import (
    MaturityState,
    MaturitySubject,
    MaturitySubjectManifest,
    OutcomeMaturityPanel,
)
from quant_pipeline.phase_09.contracts.outcomes import (
    CounterfactualMarkPanel,
    ExecutedOutcomeRecord,
    MarkQualityCount,
    MarkQualityReport,
    MarkSource,
    MarkingPolicy,
    MarketMark,
    OutcomeAssemblyReceipt,
    RealizedOutcomePanel,
    RealizedOutcomeRecord,
)


class RealizedOutcomeAndMarkQualityAssembler:
    module_id = "P9.S1.M05"

    def assemble(
        self,
        *,
        subjects: MaturitySubjectManifest,
        maturity_panel: OutcomeMaturityPanel,
        executed_outcomes: tuple[ExecutedOutcomeRecord, ...],
        market_marks: tuple[MarketMark, ...],
        policy: MarkingPolicy,
        evaluation_as_of,
        metric_family: str = "primary",
    ) -> tuple[
        RealizedOutcomePanel,
        CounterfactualMarkPanel,
        MarkQualityReport,
        OutcomeAssemblyReceipt,
    ]:
        maturity_by_subject = {
            decision.subject_id: decision
            for decision in maturity_panel.decisions
            if decision.metric_family == metric_family
        }
        executed_by_subject: dict[str, ExecutedOutcomeRecord] = {}
        future_executed_subjects: set[str] = set()
        for executed in executed_outcomes:
            effective_available_at = max(
                executed.closed_at,
                executed.settlement_at or executed.closed_at,
            )
            if effective_available_at <= evaluation_as_of:
                executed_by_subject[executed.subject_id] = executed
            else:
                future_executed_subjects.add(executed.subject_id)
        marks_by_subject: dict[str, list[MarketMark]] = {}
        for mark in market_marks:
            if mark.available_at <= evaluation_as_of:
                marks_by_subject.setdefault(mark.subject_id, []).append(mark)

        records: list[RealizedOutcomeRecord] = []
        counterfactuals: list[RealizedOutcomeRecord] = []
        stale_count = 0
        for subject in subjects.payload.subjects:
            decision = maturity_by_subject.get(subject.subject_id)
            if decision is None:
                record = self._unavailable(subject.subject_id, "P9_S1_OUTCOME_POLICY_MISSING")
            elif decision.state is MaturityState.CENSORED:
                record = RealizedOutcomeRecord(
                    subject_id=subject.subject_id,
                    evidence_class=EvidenceClass.CENSORED,
                    outcome_value=None,
                    outcome_return=None,
                    mark_price=None,
                    observed_at=None,
                    available_at=None,
                    source_id=None,
                    source_sha256=None,
                    reason_codes=("P9_S1_OUTCOME_CENSORED",),
                )
            elif not decision.eligible:
                record = self._unavailable(subject.subject_id, "P9_S1_OUTCOME_NOT_ELIGIBLE")
            elif subject.subject_id in executed_by_subject:
                executed = executed_by_subject[subject.subject_id]
                record = RealizedOutcomeRecord(
                    subject_id=subject.subject_id,
                    evidence_class=EvidenceClass.FACTUAL_EXECUTED,
                    outcome_value=executed.realized_pnl,
                    outcome_return=executed.realized_return,
                    mark_price=None,
                    observed_at=executed.closed_at,
                    available_at=executed.settlement_at or executed.closed_at,
                    source_id=executed.source_artifact_id,
                    source_sha256=executed.source_sha256,
                    quality_flags=("EXECUTED_LEDGER",),
                )
            else:
                record, stale = self._from_marks(
                    subject,
                    marks_by_subject.get(subject.subject_id, []),
                    policy,
                    evaluation_as_of,
                )
                if (
                    subject.subject_id in future_executed_subjects
                    and record.evidence_class is EvidenceClass.UNAVAILABLE
                ):
                    record = self._unavailable(
                        subject.subject_id,
                        "P9_S1_EXECUTED_OUTCOME_NOT_YET_AVAILABLE",
                    )
                stale_count += int(stale)
                if record.evidence_class in {
                    EvidenceClass.OBSERVABLE_COUNTERFACTUAL,
                    EvidenceClass.MODEL_BASED_COUNTERFACTUAL,
                    EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
                }:
                    counterfactuals.append(record)
            records.append(record)

        records.sort(key=lambda item: item.subject_id)
        counterfactuals.sort(key=lambda item: item.subject_id)
        counts = Counter(record.evidence_class for record in records)
        report = MarkQualityReport(
            counts=tuple(
                MarkQualityCount(evidence_class=evidence_class, count=counts[evidence_class])
                for evidence_class in EvidenceClass
            ),
            stale_count=stale_count,
            unavailable_count=counts[EvidenceClass.UNAVAILABLE],
            model_based_count=counts[EvidenceClass.MODEL_BASED_COUNTERFACTUAL],
        )
        panel = RealizedOutcomePanel(records=tuple(records))
        counterfactual_panel = CounterfactualMarkPanel(records=tuple(counterfactuals))
        receipt_payload = {
            "policy_id": policy.policy_id,
            "records": panel.records,
            "counterfactuals": counterfactual_panel.records,
        }
        receipt = OutcomeAssemblyReceipt(
            policy_id=policy.policy_id,
            subject_count=len(records),
            factual_count=sum(
                counts[item]
                for item in (
                    EvidenceClass.FACTUAL_EXECUTED,
                    EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
                )
            ),
            counterfactual_count=sum(
                counts[item]
                for item in (
                    EvidenceClass.OBSERVABLE_COUNTERFACTUAL,
                    EvidenceClass.MODEL_BASED_COUNTERFACTUAL,
                )
            ),
            unavailable_count=counts[EvidenceClass.UNAVAILABLE] + counts[EvidenceClass.CENSORED],
            output_sha256=payload_sha256(receipt_payload),
        )
        return panel, counterfactual_panel, report, receipt

    @staticmethod
    def _unavailable(subject_id: str, reason_code: str) -> RealizedOutcomeRecord:
        return RealizedOutcomeRecord(
            subject_id=subject_id,
            evidence_class=EvidenceClass.UNAVAILABLE,
            outcome_value=None,
            outcome_return=None,
            mark_price=None,
            observed_at=None,
            available_at=None,
            source_id=None,
            source_sha256=None,
            reason_codes=(reason_code,),
        )

    def _from_marks(
        self,
        subject: MaturitySubject,
        marks: list[MarketMark],
        policy: MarkingPolicy,
        evaluation_as_of,
    ) -> tuple[RealizedOutcomeRecord, bool]:
        matching = [
            mark
            for mark in marks
            if mark.instrument_id == subject.instrument_id
            and (not policy.require_contract_match or mark.contract_key == subject.contract_key)
        ]
        if not matching:
            return self._unavailable(subject.subject_id, "P9_S1_MARK_NO_QUOTE"), False
        matching.sort(key=lambda mark: (mark.observed_at, mark.mark_id), reverse=True)
        max_age = timedelta(seconds=policy.max_staleness_seconds)
        fresh = [mark for mark in matching if evaluation_as_of - mark.observed_at <= max_age]
        if not fresh:
            return self._unavailable(subject.subject_id, "P9_S1_MARK_STALE"), True
        chosen = self._choose_mark(fresh, policy)
        if chosen is None:
            return self._unavailable(subject.subject_id, "P9_S1_MARK_NO_QUOTE"), False
        mark, price = chosen
        value = (price - subject.reference_price) * subject.quantity * subject.contract_multiplier
        denominator = abs(subject.reference_price * subject.quantity * subject.contract_multiplier)
        outcome_return = value / denominator if denominator != 0 else None
        if mark.source is MarkSource.OFFICIAL_SETTLEMENT:
            evidence_class = EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED
            flags = ("OFFICIAL_SETTLEMENT",)
        elif mark.source is MarkSource.MODEL:
            evidence_class = EvidenceClass.MODEL_BASED_COUNTERFACTUAL
            flags = ("MODEL_BASED",)
        else:
            evidence_class = EvidenceClass.OBSERVABLE_COUNTERFACTUAL
            flags = (mark.source.value,)
        return (
            RealizedOutcomeRecord(
                subject_id=subject.subject_id,
                evidence_class=evidence_class,
                outcome_value=value,
                outcome_return=outcome_return,
                mark_price=price,
                observed_at=mark.observed_at,
                available_at=mark.available_at,
                source_id=mark.mark_id,
                source_sha256=mark.source_sha256,
                quality_flags=flags,
            ),
            False,
        )

    @staticmethod
    def _choose_mark(
        marks: list[MarketMark],
        policy: MarkingPolicy,
    ) -> tuple[MarketMark, Decimal] | None:
        if policy.prefer_official_settlement:
            settlement = next(
                (mark for mark in marks if mark.source is MarkSource.OFFICIAL_SETTLEMENT),
                None,
            )
            if settlement is not None and settlement.settlement is not None:
                return settlement, settlement.settlement
        bid_ask = next((mark for mark in marks if mark.source is MarkSource.BID_ASK), None)
        if bid_ask is not None and bid_ask.bid is not None and bid_ask.ask is not None:
            if policy.midpoint_for_bid_ask:
                return bid_ask, (bid_ask.bid + bid_ask.ask) / Decimal("2")
            return bid_ask, bid_ask.bid
        last = next((mark for mark in marks if mark.source is MarkSource.LAST), None)
        if last is not None and last.last is not None:
            return last, last.last
        model = next((mark for mark in marks if mark.source is MarkSource.MODEL), None)
        if policy.allow_model_marks and model is not None and model.model_price is not None:
            return model, model.model_price
        return None
