
"""P8.S2.M06 — compile rank into ordinal templates only."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from quant_pipeline.phase_08_contracts.enums import ConfidenceState, ScoreSemantics

from ..context import S2ExecutionContext
from ..contracts.enums import (
    ConfidenceEvidenceState,
    OrdinalConstraintType,
    PairwiseMode,
    StaticActionState,
)
from ..contracts.preferences import (
    ConfidenceEvidenceHint,
    LexicographicTier,
    OrdinalPenaltyTemplate,
    OrdinalPreferenceConstraintSet,
    OrdinalSemanticsProof,
    PairwiseOrdinalConstraint,
)
from ..contracts.results import M06Result
from ..errors import OrdinalSemanticsError
from ..module_support import build_receipt, seal
from ..policies import OrdinalPreferencePolicy

MODULE_ID = "P8.S2.M06"


def run_module(bundle, m05, *, context: S2ExecutionContext, policy: OrdinalPreferencePolicy) -> M06Result:
    forwarded = set(m05.static_action_universe.forwarded_candidate_ids)
    ranked = [row for row in bundle.validated_handoff.handoff.ranked if row.candidate_id in forwarded]
    by_group: dict[str, dict[int, list[object]]] = defaultdict(lambda: defaultdict(list))
    reason_codes: set[str] = set()
    hints: list[ConfidenceEvidenceHint] = []
    for row in ranked:
        by_group[row.comparison_group_id][row.rank].append(row)
        if row.score_semantics is not ScoreSemantics.ORDINAL:
            reason_codes.add("CARDINAL_SCORE_VALUE_NOT_CONSUMED_BY_S2")
        if row.confidence_state is ConfidenceState.CALIBRATED:
            if row.confidence_calibration_ref is None:
                raise OrdinalSemanticsError("calibrated confidence lacks calibration reference")
            hints.append(ConfidenceEvidenceHint(
                candidate_id=row.candidate_id,
                state=ConfidenceEvidenceState.CALIBRATED_REFERENCE_AVAILABLE,
                calibration_artifact_hash=row.confidence_calibration_ref.content_sha256,
            ))
        elif row.confidence_state is ConfidenceState.UNCALIBRATED:
            hints.append(ConfidenceEvidenceHint(candidate_id=row.candidate_id, state=ConfidenceEvidenceState.UNCALIBRATED))
        else:
            hints.append(ConfidenceEvidenceHint(candidate_id=row.candidate_id, state=ConfidenceEvidenceState.UNAVAILABLE))
    tiers: list[LexicographicTier] = []
    constraints: list[PairwiseOrdinalConstraint] = []
    for group_id in sorted(by_group):
        rank_map = by_group[group_id]
        ordered_ranks = sorted(rank_map)
        for rank in ordered_ranks:
            ids = tuple(sorted(row.candidate_id for row in rank_map[rank]))
            tiers.append(LexicographicTier(comparison_group_id=group_id, rank=rank, candidate_ids=ids))
        rank_pairs: list[tuple[int, int]] = []
        if policy.pairwise_mode is PairwiseMode.ADJACENT_TIERS:
            rank_pairs = list(zip(ordered_ranks, ordered_ranks[1:], strict=False))
        else:
            rank_pairs = [(left, right) for index, left in enumerate(ordered_ranks) for right in ordered_ranks[index + 1:]]
        for preferred_rank, less_rank in rank_pairs:
            for preferred in sorted(rank_map[preferred_rank], key=lambda row: row.candidate_id):
                for less in sorted(rank_map[less_rank], key=lambda row: row.candidate_id):
                    constraint_id = f"ordinal:{group_id}:{preferred.candidate_id}:{less.candidate_id}"
                    constraints.append(PairwiseOrdinalConstraint(
                        constraint_id=constraint_id,
                        constraint_type=OrdinalConstraintType.PREFERRED_OVER,
                        comparison_group_id=group_id,
                        preferred_candidate_id=preferred.candidate_id,
                        less_preferred_candidate_id=less.candidate_id,
                        preferred_rank=preferred_rank,
                        less_preferred_rank=less_rank,
                    ))
    penalties = tuple(OrdinalPenaltyTemplate(
        constraint_id=row.constraint_id,
        inversion_unit_penalty=Decimal("1"),
    ) for row in constraints)
    result = seal(OrdinalPreferenceConstraintSet(
        contract_version="P8_ORDINAL_PREFERENCE_CONSTRAINT_SET_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        pairwise_constraints=tuple(constraints),
        lexicographic_tiers=tuple(tiers),
        penalty_templates=penalties,
        confidence_hints=tuple(sorted(hints, key=lambda item: item.candidate_id)),
        proof=OrdinalSemanticsProof(pairwise_mode=policy.pairwise_mode),
        reason_codes=tuple(sorted(reason_codes)),
        content_sha256="0" * 64,
    ))
    receipt = build_receipt(
        module_id=MODULE_ID,
        inputs=(bundle.validated_handoff, m05.static_action_universe),
        output=result,
        computed_at=context.computed_at,
    )
    return M06Result(ordinal_preferences=result, receipt=receipt)

run_m06 = run_module
