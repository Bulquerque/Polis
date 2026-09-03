from __future__ import annotations

from .enums import AdaptationDecision, AdaptationKind, ReasonCode
from .models_evidence import AdaptationBound, AdaptationRecord, AdaptationRequest


_INCREASE_KINDS = {
    AdaptationKind.INCREASE_LIQUIDITY_HAIRCUT,
    AdaptationKind.INCREASE_MARGIN_BUFFER,
    AdaptationKind.WIDEN_NO_TRADE_REGION,
}
_DECREASE_KINDS = {
    AdaptationKind.DECREASE_RISK_CAP,
    AdaptationKind.DECREASE_PARTICIPATION_RATE,
}


def _is_conservative(request: AdaptationRequest) -> bool:
    if request.kind in _INCREASE_KINDS:
        return request.proposed_value >= request.previous_value
    if request.kind in _DECREASE_KINDS:
        return request.proposed_value <= request.previous_value
    if request.kind is AdaptationKind.ENTER_RESTRICTED_MODE:
        return request.proposed_value >= request.previous_value
    return False


def _bound_map(bounds: tuple[AdaptationBound, ...]) -> dict[AdaptationKind, AdaptationBound]:
    result = {bound.kind: bound for bound in bounds}
    if len(result) != len(bounds):
        raise ValueError("duplicate adaptation bound")
    return result


def evaluate_adaptations(
    requests: tuple[AdaptationRequest, ...],
    bounds: tuple[AdaptationBound, ...],
) -> tuple[AdaptationRecord, ...]:
    bound_by_kind = _bound_map(bounds)
    records: list[AdaptationRecord] = []
    for request in requests:
        reasons: list[ReasonCode] = []
        if not _is_conservative(request):
            reasons.append(ReasonCode.ADAPTATION_NON_CONSERVATIVE)
        bound = bound_by_kind.get(request.kind)
        if bound is None or not bound.minimum_value <= request.proposed_value <= bound.maximum_value:
            reasons.append(ReasonCode.ADAPTATION_OUT_OF_BOUNDS)
        records.append(AdaptationRecord(
            adaptation_id=request.adaptation_id,
            kind=request.kind,
            previous_value=request.previous_value,
            proposed_value=request.proposed_value,
            decision=AdaptationDecision.REJECTED if reasons else AdaptationDecision.ACCEPTED,
            reason_codes=tuple(reasons),
        ))
    return tuple(records)
