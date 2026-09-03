"""P9.S8.M01 — forecast, resolver, ensemble, and view attribution.

The baseline is leave-one-component-out loss attribution. It is associational,
not causal. Historical weights and OOF-qualified losses are required for strong
claims. A financial PnL effect can be supplied when an observable ablation was
executed; otherwise the result remains score-space attribution only.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

import numpy as np
from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class ForecastComponentObservation(StrictModel):
    observation_id: NonEmptyStr
    target_id: NonEmptyStr
    horizon_id: NonEmptyStr
    regime_id: NonEmptyStr
    component_id: NonEmptyStr
    component_kind: NonEmptyStr
    consumed: bool
    historical_weight: float
    ensemble_loss: float = Field(ge=0.0)
    ablated_loss: float | None = Field(default=None, ge=0.0)
    component_prediction: float | None = None
    oof_qualified: bool
    observable_pnl_with_component: float | None = None
    observable_pnl_without_component: float | None = None
    evidence_class: EvidenceClass

    @model_validator(mode="after")
    def validate_component(self) -> "ForecastComponentObservation":
        if not self.consumed and self.historical_weight != 0.0:
            raise ValueError("unconsumed component must have zero historical weight")
        if (self.observable_pnl_with_component is None) != (
            self.observable_pnl_without_component is None
        ):
            raise ValueError("both PnL ablation values must be provided together")
        return self


class ForecastAttributionPolicy(StrictModel):
    require_oof_for_qualified: bool = True
    collinearity_threshold: float = Field(default=0.98, gt=0.0, le=1.0)
    minimum_observations: int = Field(default=3, ge=1)


class ComponentAttribution(StrictModel):
    component_id: NonEmptyStr
    component_kind: NonEmptyStr
    observation_count: int = Field(ge=0)
    mean_historical_weight: float
    mean_loss_increase_when_removed: float | None
    aggregate_pnl_effect: float | None
    quality: AttributionQuality
    evidence_class: EvidenceClass
    reason_codes: tuple[NonEmptyStr, ...] = ()


class CollinearityPair(StrictModel):
    first_component_id: NonEmptyStr
    second_component_id: NonEmptyStr
    correlation: float = Field(ge=-1.0, le=1.0)


class ForecastAttributionResult(StrictModel):
    components: tuple[ComponentAttribution, ...]
    collinearity_pairs: tuple[CollinearityPair, ...]
    aggregate_pnl_effect: float | None
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def attribute_forecast_components(
    observations: tuple[ForecastComponentObservation, ...],
    policy: ForecastAttributionPolicy,
) -> ForecastAttributionResult:
    """Aggregate leave-one-out loss and observable PnL effects by component."""

    by_component: dict[str, list[ForecastComponentObservation]] = defaultdict(list)
    for observation in observations:
        by_component[observation.component_id].append(observation)

    components: list[ComponentAttribution] = []
    global_reasons: set[str] = set()
    total_pnl = 0.0
    has_any_pnl = False
    for component_id in sorted(by_component):
        rows = by_component[component_id]
        reasons: set[str] = set()
        qualified_rows = [row for row in rows if row.consumed]
        ablation_deltas = [
            row.ablated_loss - row.ensemble_loss
            for row in qualified_rows
            if row.ablated_loss is not None
        ]
        pnl_deltas = [
            row.observable_pnl_with_component - row.observable_pnl_without_component
            for row in qualified_rows
            if row.observable_pnl_with_component is not None
            and row.observable_pnl_without_component is not None
        ]
        if not qualified_rows:
            quality = AttributionQuality.INSUFFICIENT_EVIDENCE
            reasons.add("P9_ATTRIBUTION_COMPONENT_NOT_CONSUMED")
        elif len(qualified_rows) < policy.minimum_observations:
            quality = AttributionQuality.INSUFFICIENT_EVIDENCE
            reasons.add("P9_ATTRIBUTION_COMPONENT_SAMPLE_INSUFFICIENT")
        elif policy.require_oof_for_qualified and any(
            not row.oof_qualified for row in qualified_rows
        ):
            quality = AttributionQuality.LIMITED
            reasons.add("P9_ATTRIBUTION_COMPONENT_OOF_MISSING")
        elif not ablation_deltas:
            quality = AttributionQuality.NOT_IDENTIFIABLE
            reasons.add("P9_ATTRIBUTION_FORECAST_NOT_IDENTIFIABLE")
        else:
            quality = AttributionQuality.QUALIFIED
        pnl_effect = sum(pnl_deltas) if pnl_deltas else None
        if pnl_effect is not None:
            total_pnl += pnl_effect
            has_any_pnl = True
        evidence = _weakest_evidence(row.evidence_class for row in qualified_rows or rows)
        components.append(
            ComponentAttribution(
                component_id=component_id,
                component_kind=rows[0].component_kind,
                observation_count=len(qualified_rows),
                mean_historical_weight=(
                    fmean(row.historical_weight for row in qualified_rows)
                    if qualified_rows
                    else 0.0
                ),
                mean_loss_increase_when_removed=(
                    fmean(ablation_deltas) if ablation_deltas else None
                ),
                aggregate_pnl_effect=pnl_effect,
                quality=quality,
                evidence_class=evidence,
                reason_codes=tuple(sorted(reasons)),
            )
        )
        global_reasons.update(reasons)

    pairs = _find_collinearity(observations, policy.collinearity_threshold)
    if pairs:
        global_reasons.add("P9_ATTRIBUTION_VIEW_COLLINEARITY_UNRESOLVED")
    overall_quality = _aggregate_quality(item.quality for item in components)
    payload = {
        "components": [item.model_dump(mode="json") for item in components],
        "pairs": [item.model_dump(mode="json") for item in pairs],
        "aggregate_pnl_effect": total_pnl if has_any_pnl else None,
        "quality": overall_quality,
        "reason_codes": sorted(global_reasons),
    }
    return ForecastAttributionResult(
        components=tuple(components),
        collinearity_pairs=tuple(pairs),
        aggregate_pnl_effect=total_pnl if has_any_pnl else None,
        quality=overall_quality,
        reason_codes=tuple(sorted(global_reasons)),
        result_sha256=payload_sha256(payload),
    )


def _find_collinearity(
    observations: tuple[ForecastComponentObservation, ...],
    threshold: float,
) -> list[CollinearityPair]:
    values: dict[str, dict[str, float]] = defaultdict(dict)
    for row in observations:
        if row.component_prediction is not None and row.consumed:
            values[row.component_id][row.observation_id] = row.component_prediction
    result: list[CollinearityPair] = []
    ids = sorted(values)
    for index, first in enumerate(ids):
        for second in ids[index + 1 :]:
            common = sorted(set(values[first]) & set(values[second]))
            if len(common) < 3:
                continue
            left = np.asarray([values[first][key] for key in common], dtype=np.float64)
            right = np.asarray([values[second][key] for key in common], dtype=np.float64)
            if np.std(left) == 0.0 or np.std(right) == 0.0:
                continue
            correlation = float(np.corrcoef(left, right)[0, 1])
            if abs(correlation) >= threshold:
                result.append(
                    CollinearityPair(
                        first_component_id=first,
                        second_component_id=second,
                        correlation=correlation,
                    )
                )
    return result


def _weakest_evidence(values: object) -> EvidenceClass:
    order = {
        EvidenceClass.FACTUAL_EXECUTED: 5,
        EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED: 4,
        EvidenceClass.OBSERVABLE_COUNTERFACTUAL: 3,
        EvidenceClass.MODEL_BASED_COUNTERFACTUAL: 2,
        EvidenceClass.CENSORED: 1,
        EvidenceClass.UNAVAILABLE: 0,
    }
    items = tuple(values)  # type: ignore[arg-type]
    return min(items, key=order.__getitem__) if items else EvidenceClass.UNAVAILABLE


def _aggregate_quality(values: object) -> AttributionQuality:
    items = tuple(values)  # type: ignore[arg-type]
    if not items:
        return AttributionQuality.INSUFFICIENT_EVIDENCE
    if AttributionQuality.INVALID in items:
        return AttributionQuality.INVALID
    if AttributionQuality.NOT_IDENTIFIABLE in items:
        return AttributionQuality.NOT_IDENTIFIABLE
    if AttributionQuality.INSUFFICIENT_EVIDENCE in items:
        return AttributionQuality.INSUFFICIENT_EVIDENCE
    if AttributionQuality.LIMITED in items:
        return AttributionQuality.LIMITED
    return AttributionQuality.QUALIFIED
