
"""P8.S2.M03 — exact/scale equivalence only; soft similarity is a request, not exclusion."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from itertools import combinations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256

from ..context import S2ExecutionContext
from ..contracts.equivalence import (
    EquivalenceGroup,
    EquivalenceMember,
    ExactEquivalenceGroupPanel,
    SoftSimilarityRequest,
    SoftSimilarityRequestPanel,
)
from ..contracts.enums import EquivalenceType
from ..contracts.results import M03Result
from ..errors import EquivalenceIntegrityError
from ..module_support import build_receipt, seal
from ..policies import EquivalencePolicy

MODULE_ID = "P8.S2.M03"


def _leg_key(leg) -> tuple[object, ...]:
    return (
        leg.instrument_id, leg.instrument_type, leg.contract_multiplier, leg.strike,
        leg.expiration, leg.exercise_style.value, leg.settlement_type.value, leg.instrument_master_hash,
    )


def _leg_map(candidate) -> dict[tuple[object, ...], Decimal]:
    return {_leg_key(leg): leg.signed_contract_quantity_per_candidate_unit for leg in candidate.legs}


def _scale_factor(left, right) -> Decimal | None:
    left_map, right_map = _leg_map(left), _leg_map(right)
    if set(left_map) != set(right_map):
        return None
    ratios: set[Decimal] = set()
    for key in sorted(left_map, key=repr):
        left_value, right_value = left_map[key], right_map[key]
        if left_value == 0 or right_value == 0 or left_value * right_value <= 0:
            return None
        ratios.add(right_value / left_value)
    if len(ratios) != 1:
        return None
    factor = ratios.pop()
    if factor <= 0:
        return None
    numeric_fields = ("unit_entry_cost", "unit_maximum_loss", "margin_per_unit")
    for field_name in numeric_fields:
        left_value = getattr(left.unit_economics, field_name)
        right_value = getattr(right.unit_economics, field_name)
        if (left_value is None) != (right_value is None):
            return None
        if left_value is not None and right_value != left_value * factor:
            return None
    if left.unit_economics.entry_cost_status != right.unit_economics.entry_cost_status:
        return None
    if left.unit_economics.payoff_status != right.unit_economics.payoff_status:
        return None
    if left.unit_economics.maximum_loss_status != right.unit_economics.maximum_loss_status:
        return None
    if left.unit_economics.lifecycle_status != right.unit_economics.lifecycle_status:
        return None
    return factor


def run_module(bundle, m01, m02, *, context: S2ExecutionContext, policy: EquivalencePolicy) -> M03Result:
    ranked = {row.candidate_id: row for row in bundle.validated_handoff.handoff.ranked}
    candidates = {row.candidate_id: row for row in m01.normalized_intents.candidates}
    groups: list[EquivalenceGroup] = []
    used_pairs: set[tuple[str, str]] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    for left_id, right_id in combinations(sorted(candidates), 2):
        left, right = candidates[left_id], candidates[right_id]
        if left.currency != right.currency:
            continue
        factor = _scale_factor(left, right)
        if factor is None:
            continue
        pair = (left_id, right_id)
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)
        used_pairs.add(pair)
    unseen = set(adjacency)
    while unseen:
        start = min(unseen)
        stack = [start]
        component: list[str] = []
        unseen.remove(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        ids = sorted(component, key=lambda cid: (ranked[cid].rank, cid))
        representative_id = ids[0]
        representative = candidates[representative_id]
        members: list[EquivalenceMember] = []
        exact = True
        for candidate_id in ids:
            if candidate_id == representative_id:
                factor = Decimal("1")
            else:
                factor = _scale_factor(representative, candidates[candidate_id])
                if factor is None:
                    raise EquivalenceIntegrityError("equivalence component lost transitive scale relation")
            if factor != 1:
                exact = False
            members.append(EquivalenceMember(
                candidate_id=candidate_id,
                scale_factor_from_representative=factor,
            ))
        same_group = len({candidates[cid].comparison_group_id for cid in ids}) == 1
        same_canonical = len({candidates[cid].canonical_candidate_id for cid in ids}) == 1
        same_p5 = len({candidates[cid].p5_evidence_signature_hash for cid in ids}) == 1
        hard = (
            (same_group or not policy.require_same_comparison_group_for_hard_redundancy)
            and (same_canonical or not policy.require_same_canonical_candidate_id_for_hard_redundancy)
            and (same_p5 or not policy.require_same_p5_belief_for_hard_redundancy)
        )
        reason_codes: list[str] = []
        if not same_group: reason_codes.append("CROSS_GROUP_PHYSICAL_EQUIVALENCE_NOT_REDUNDANT")
        if not same_canonical: reason_codes.append("DIFFERENT_CANONICAL_CANDIDATE_NOT_REDUNDANT")
        if not same_p5: reason_codes.append("DIFFERENT_P5_EVIDENCE_SIGNATURE")
        signature = canonical_sha256(tuple(sorted((_leg_key(leg), leg.signed_contract_quantity_per_candidate_unit) for leg in representative.legs)))
        groups.append(EquivalenceGroup(
            equivalence_group_id=f"equivalence:{canonical_sha256(tuple(ids))[:20]}",
            equivalence_type=EquivalenceType.EXACT_PHYSICAL if exact else EquivalenceType.SCALE_EQUIVALENT,
            representative_candidate_id=representative_id,
            comparison_group_id=representative.comparison_group_id,
            members=tuple(members),
            physical_signature_hash=signature,
            hard_redundant_eligible=hard,
            reason_codes=tuple(reason_codes),
        ))

    handoff_groups = {row.comparison_group_id: row for row in bundle.validated_handoff.handoff.comparison_groups}
    requests: list[SoftSimilarityRequest] = []
    for left_id, right_id in combinations(sorted(candidates), 2):
        if (left_id, right_id) in used_pairs:
            continue
        left, right = candidates[left_id], candidates[right_id]
        if left.comparison_group_id != right.comparison_group_id:
            continue
        left_instruments = {leg.instrument_id for leg in left.legs}
        right_instruments = {leg.instrument_id for leg in right.legs}
        scope = set(handoff_groups[left.comparison_group_id].underlying_scope)
        shared_instruments = tuple(sorted(left_instruments & right_instruments))
        dimensions: list[str] = []
        if shared_instruments: dimensions.append("SCENARIO_PNL_SIMILARITY")
        if scope: dimensions.extend(("TAIL_COMOVEMENT", "FACTOR_EXPOSURE_SIMILARITY"))
        if left.objective_family == right.objective_family: dimensions.append("OBJECTIVE_FAMILY_CONCENTRATION")
        if dimensions:
            requests.append(SoftSimilarityRequest(
                request_id=f"similarity:{canonical_sha256((left_id, right_id, tuple(dimensions)))[:20]}",
                left_candidate_id=left_id,
                right_candidate_id=right_id,
                comparison_group_id=left.comparison_group_id,
                shared_instrument_ids=shared_instruments,
                shared_underlying_scope=tuple(sorted(scope)),
                requested_dimensions=tuple(sorted(set(dimensions))),
            ))
    group_panel = seal(ExactEquivalenceGroupPanel(
        contract_version="P8_EXACT_EQUIVALENCE_GROUP_PANEL_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        groups=tuple(sorted(groups, key=lambda item: item.equivalence_group_id)),
        content_sha256="0" * 64,
    ))
    request_panel = seal(SoftSimilarityRequestPanel(
        contract_version="P8_SOFT_SIMILARITY_REQUEST_PANEL_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        requests=tuple(sorted(requests, key=lambda item: item.request_id)),
        content_sha256="0" * 64,
    ))
    receipt = build_receipt(
        module_id=MODULE_ID,
        inputs=(m01.normalized_intents, m02.exposure_graph),
        output=(group_panel, request_panel),
        computed_at=context.computed_at,
    )
    return M03Result(equivalence_groups=group_panel, soft_similarity_requests=request_panel, receipt=receipt)

run_m03 = run_module
