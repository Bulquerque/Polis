"""P9.S3.M02 — purged and embargoed walk-forward assignment."""

from __future__ import annotations

from collections import Counter

from .common import content_sha256
from .errors import TemporalIntegrityError
from .reason_codes import ReasonCode
from .temporal_models import (
    FoldAssignment,
    FoldAssignmentPanel,
    SampleRecord,
    SampleRole,
    SplitCount,
    SplitIntegrityReceipt,
    TemporalEvaluationPlan,
)


def _label_overlaps(record: SampleRecord, start, end) -> bool:
    return record.label_start_time < end and record.label_end_time > start


def build_purged_walk_forward_assignments(
    plan: TemporalEvaluationPlan,
    records: tuple[SampleRecord, ...],
) -> tuple[FoldAssignmentPanel, SplitIntegrityReceipt]:
    """Assign samples to folds with point-in-time checks and interval purging."""

    ids = [record.record_id for record in records]
    duplicates = [item for item, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise TemporalIntegrityError(
            f"{ReasonCode.DUPLICATE_RECORD_ID.value}: {','.join(sorted(duplicates))}"
        )

    ordered = tuple(
        sorted(
            records,
            key=lambda item: (item.decision_time, item.entity_id, item.record_id),
        )
    )
    assignments: list[FoldAssignment] = []
    counts: list[SplitCount] = []
    global_reasons: set[str] = set()

    for fold in plan.folds:
        role_counts = Counter()
        purged = 0
        pit_rejected = 0
        for record in ordered:
            reasons: list[str] = []
            role = SampleRole.EXCLUDED

            if (
                record.available_at > record.decision_time
                or record.vintage_time > record.decision_time
            ):
                reasons.append(ReasonCode.PIT_AVAILABILITY_VIOLATION.value)
                pit_rejected += 1
                global_reasons.add(ReasonCode.PIT_AVAILABILITY_VIOLATION.value)
            elif fold.train_window.contains(record.decision_time):
                if _label_overlaps(record, fold.tuning_window.start, fold.test_window.end):
                    reasons.append(ReasonCode.LABEL_OVERLAP_PURGED.value)
                    purged += 1
                else:
                    role = SampleRole.TRAIN
            elif fold.tuning_window.contains(record.decision_time):
                if _label_overlaps(record, fold.test_window.start, fold.test_window.end):
                    reasons.append(ReasonCode.LABEL_OVERLAP_PURGED.value)
                    purged += 1
                else:
                    role = SampleRole.TUNING
            elif fold.test_window.contains(record.decision_time):
                role = SampleRole.TEST

            role_counts[role.value] += 1
            assignments.append(
                FoldAssignment(
                    fold_id=fold.fold_id,
                    record_id=record.record_id,
                    entity_id=record.entity_id,
                    role=role,
                    reason_codes=tuple(reasons),
                )
            )

        fold_count = SplitCount(
            fold_id=fold.fold_id,
            train_count=role_counts[SampleRole.TRAIN.value],
            tuning_count=role_counts[SampleRole.TUNING.value],
            test_count=role_counts[SampleRole.TEST.value],
            excluded_count=role_counts[SampleRole.EXCLUDED.value],
            purged_count=purged,
            pit_rejected_count=pit_rejected,
        )
        counts.append(fold_count)
        if (
            fold_count.train_count == 0
            or fold_count.tuning_count == 0
            or fold_count.test_count == 0
        ):
            global_reasons.add(ReasonCode.SPLIT_EMPTY.value)

    body = {"plan_id": plan.plan_id, "assignments": assignments}
    panel = FoldAssignmentPanel(
        plan_id=plan.plan_id,
        assignments=tuple(assignments),
        content_sha256=content_sha256(body),
    )
    status = "VALID" if not global_reasons else "INVALID"
    receipt_body = {
        "plan_id": plan.plan_id,
        "status": status,
        "counts": counts,
        "reasons": sorted(global_reasons),
    }
    receipt = SplitIntegrityReceipt(
        plan_id=plan.plan_id,
        status=status,
        counts=tuple(counts),
        reason_codes=tuple(sorted(global_reasons)),
        content_sha256=content_sha256(receipt_body),
    )
    return panel, receipt
