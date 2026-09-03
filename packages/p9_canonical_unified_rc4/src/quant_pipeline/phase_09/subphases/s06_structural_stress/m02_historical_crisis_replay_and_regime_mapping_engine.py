from __future__ import annotations

from quant_pipeline.phase_09.errors import InvariantViolation

import math
from typing import NamedTuple

from .contracts import EvidenceClass, ReplayMode, S6State
from .models import (
    ExposureMappingResult,
    ExposureRecord,
    FactorMapping,
    HistoricalCrisisReplayResult,
    HistoricalReplayRequest,
    ReplayPoint,
)


class _ResolvedExposure(NamedTuple):
    exposure: ExposureRecord
    factor_index: int | None
    mapping_scale: float
    evidence_class: EvidenceClass


def _scenario_exists(request: HistoricalReplayRequest) -> bool:
    return any(
        item.scenario.scenario_id == request.scenario_id
        for item in request.registry.scenarios
    )


def _resolve_exposure(
    request: HistoricalReplayRequest,
    exposure: ExposureRecord,
    factor_index: dict[str, int],
    explicit_mappings: dict[str, FactorMapping],
) -> tuple[ExposureMappingResult, _ResolvedExposure]:
    if exposure.current_factor_id in factor_index:
        historical_factor_id = exposure.current_factor_id
        scale = 1.0
        evidence_class = request.factor_path.evidence_classes[
            factor_index[historical_factor_id]
        ]
    elif exposure.current_factor_id in explicit_mappings:
        mapping = explicit_mappings[exposure.current_factor_id]
        historical_factor_id = mapping.historical_factor_id
        scale = mapping.scale
        evidence_class = mapping.evidence_class
    else:
        historical_factor_id = None
        scale = 0.0
        evidence_class = EvidenceClass.UNAVAILABLE
    index = None if historical_factor_id is None else factor_index.get(historical_factor_id)
    mapped = index is not None
    row = ExposureMappingResult(
        exposure_id=exposure.exposure_id,
        current_factor_id=exposure.current_factor_id,
        historical_factor_id=historical_factor_id if mapped else None,
        mapping_scale=scale if mapped else None,
        evidence_class=evidence_class,
        mapped=mapped,
        notional=exposure.notional,
    )
    return row, _ResolvedExposure(exposure, index, scale, evidence_class)


def _resolve_exposures(
    request: HistoricalReplayRequest,
) -> tuple[tuple[ExposureMappingResult, ...], tuple[_ResolvedExposure, ...], float, float]:
    factor_index = {
        factor_id: index for index, factor_id in enumerate(request.factor_path.factor_ids)
    }
    explicit_mappings = {mapping.current_factor_id: mapping for mapping in request.mappings}
    rows: list[ExposureMappingResult] = []
    resolved: list[_ResolvedExposure] = []
    mapped_notional = 0.0
    unmapped_notional = 0.0
    for exposure in request.exposures:
        row, item = _resolve_exposure(
            request,
            exposure,
            factor_index,
            explicit_mappings,
        )
        rows.append(row)
        resolved.append(item)
        if row.mapped:
            mapped_notional += abs(exposure.notional)
        else:
            unmapped_notional += abs(exposure.notional)
    return tuple(rows), tuple(resolved), mapped_notional, unmapped_notional


def _time_scale(request: HistoricalReplayRequest, index: int) -> float:
    if request.replay_mode is ReplayMode.STATIC_EXPOSURE:
        return 1.0
    if request.frozen_exposure_scales is None:
        raise InvariantViolation("dynamic replay requires frozen exposure scales")
    return request.frozen_exposure_scales[index]


def _point_pnl(
    request: HistoricalReplayRequest,
    resolved: tuple[_ResolvedExposure, ...],
    time_index: int,
) -> tuple[float, float]:
    total = 0.0
    modelled = 0.0
    multiplier = _time_scale(request, time_index)
    for item in resolved:
        if item.factor_index is None:
            continue
        shock = request.factor_path.values[time_index][item.factor_index] * item.mapping_scale
        pnl = multiplier * (
            item.exposure.linear_sensitivity * shock
            + 0.5 * item.exposure.quadratic_sensitivity * shock * shock
        )
        total += pnl
        if item.evidence_class not in {
            EvidenceClass.OBSERVED_HISTORICAL,
            EvidenceClass.OBSERVED_LIVE,
        }:
            modelled += pnl
    return total, modelled


def _replay_path(
    request: HistoricalReplayRequest,
    resolved: tuple[_ResolvedExposure, ...],
    unmapped_notional: float,
) -> tuple[tuple[ReplayPoint, ...], float, float]:
    path: list[ReplayPoint] = []
    cumulative = 0.0
    total_abs_pnl = 0.0
    total_modelled_abs_pnl = 0.0
    for time_index, timestamp in enumerate(request.factor_path.timestamps):
        point_pnl, modelled_pnl = _point_pnl(request, resolved, time_index)
        cumulative += point_pnl
        total_abs_pnl += abs(point_pnl)
        total_modelled_abs_pnl += abs(modelled_pnl)
        path.append(
            ReplayPoint(
                timestamp=timestamp,
                pnl=point_pnl,
                cumulative_pnl=cumulative,
                mapped_pnl=point_pnl,
                modelled_pnl=modelled_pnl,
                unmapped_notional=unmapped_notional,
            )
        )
    return tuple(path), total_abs_pnl, total_modelled_abs_pnl


def _status_and_limits(
    request: HistoricalReplayRequest,
    mapped_share: float,
    modelled_share: float,
    recovery_included: bool,
) -> tuple[S6State, tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    limitations: list[str] = []
    if mapped_share < request.policy.minimum_mapped_exposure_share:
        reasons.append("P9_STRESS_HISTORICAL_MAPPING_INCOMPLETE")
        limitations.append("material exposure remains unmapped")
    if modelled_share > request.policy.maximum_modelled_pnl_share:
        reasons.append("P9_STRESS_MODELLED_PNL_SHARE_MATERIAL")
        limitations.append("modelled PnL share exceeds policy")
    if request.policy.require_recovery_path and not recovery_included:
        reasons.append("P9_STRESS_RECOVERY_PATH_MISSING")
        limitations.append("historical replay does not include a measurable recovery")
    if mapped_share < request.policy.minimum_mapped_exposure_share:
        status = S6State.MATERIAL_EXPOSURE_UNMAPPED
    elif limitations:
        status = S6State.SUCCESS_WITH_MAPPING_LIMITATIONS
    else:
        status = S6State.SUCCESS
    return status, tuple(reasons), tuple(limitations)


def _invalid_scenario_result(request: HistoricalReplayRequest) -> HistoricalCrisisReplayResult:
    return HistoricalCrisisReplayResult(
        status=S6State.INVALID,
        scenario_id=request.scenario_id,
        replay_mode=request.replay_mode,
        mappings=(),
        path=(),
        mapped_exposure_share=0.0,
        modelled_pnl_share=0.0,
        unmapped_notional=sum(abs(exposure.notional) for exposure in request.exposures),
        worst_cumulative_pnl=0.0,
        recovery_included=False,
        reason_codes=("P9_STRESS_SCENARIO_NOT_COMMITTED",),
    )


def replay_historical_crisis(request: HistoricalReplayRequest) -> HistoricalCrisisReplayResult:
    """Replay a historical factor path against frozen current exposures."""

    if not _scenario_exists(request):
        return _invalid_scenario_result(request)
    mappings, resolved, mapped_notional, unmapped_notional = _resolve_exposures(request)
    path, total_abs_pnl, total_modelled_abs_pnl = _replay_path(
        request,
        resolved,
        unmapped_notional,
    )
    total_notional = sum(abs(exposure.notional) for exposure in request.exposures)
    mapped_share = 0.0 if total_notional == 0 else mapped_notional / total_notional
    modelled_share = (
        0.0
        if total_abs_pnl == 0
        else min(1.0, total_modelled_abs_pnl / total_abs_pnl)
    )
    recovery_included = (
        len(path) >= 3
        and path[-1].cumulative_pnl > min(point.cumulative_pnl for point in path)
    )
    status, reasons, limitations = _status_and_limits(
        request,
        mapped_share,
        modelled_share,
        recovery_included,
    )
    worst = min((point.cumulative_pnl for point in path), default=0.0)
    if not math.isfinite(worst):
        raise ValueError("historical replay produced non-finite PnL")
    return HistoricalCrisisReplayResult(
        status=status,
        scenario_id=request.scenario_id,
        replay_mode=request.replay_mode,
        mappings=mappings,
        path=path,
        mapped_exposure_share=mapped_share,
        modelled_pnl_share=modelled_share,
        unmapped_notional=unmapped_notional,
        worst_cumulative_pnl=worst,
        recovery_included=recovery_included,
        reason_codes=reasons,
        limitations=limitations,
    )
