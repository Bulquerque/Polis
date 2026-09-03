"""P9.S8.M04 — selection, sizing, constraints, discretization, and netting."""

from __future__ import annotations


from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class CandidateAllocationRecord(StrictModel):
    candidate_id: NonEmptyStr
    selected: bool
    ranking_position: int = Field(ge=1)
    realized_unit_pnl: float
    reference_quantity: float = 1.0
    unconstrained_quantity: float
    constrained_quantity: float
    discrete_quantity: float
    constraint_reason_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_quantities(self) -> "CandidateAllocationRecord":
        if not self.selected and any(
            abs(value) > 0.0
            for value in (
                self.unconstrained_quantity,
                self.constrained_quantity,
                self.discrete_quantity,
            )
        ):
            raise ValueError("unselected candidate cannot carry quantity")
        return self


class VirtualCandidateLedgerItem(StrictModel):
    candidate_id: NonEmptyStr
    discrete_quantity: float
    realized_virtual_pnl: float
    instrument_quantities: tuple[tuple[NonEmptyStr, float], ...]


class PhysicalPositionLedgerItem(StrictModel):
    instrument_id: NonEmptyStr
    net_quantity: float
    realized_physical_pnl: float


class PortfolioAttributionPolicy(StrictModel):
    reconciliation_tolerance: float = Field(default=1e-8, ge=0.0)


class CandidateAllocationEffect(StrictModel):
    candidate_id: NonEmptyStr
    selection_effect: float
    sizing_effect: float
    constraint_effect: float
    discretization_effect: float
    total_virtual_pnl: float


class PortfolioAttributionResult(StrictModel):
    candidate_effects: tuple[CandidateAllocationEffect, ...]
    selection_effect: float
    sizing_effect: float
    constraint_effect: float
    discretization_effect: float
    netting_diversification_effect: float
    virtual_pnl: float
    physical_pnl: float
    dual_book_difference: float
    aggregate_pnl_effect: float
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def attribute_portfolio_construction(
    allocations: tuple[CandidateAllocationRecord, ...],
    virtual_ledger: tuple[VirtualCandidateLedgerItem, ...],
    physical_ledger: tuple[PhysicalPositionLedgerItem, ...],
    policy: PortfolioAttributionPolicy,
) -> PortfolioAttributionResult:
    """Apply a pre-registered sequential decomposition and reconcile the dual book."""

    allocation_by_id = {item.candidate_id: item for item in allocations}
    if len(allocation_by_id) != len(allocations):
        raise ValueError("duplicate candidate allocation")
    virtual_by_id = {item.candidate_id: item for item in virtual_ledger}
    if len(virtual_by_id) != len(virtual_ledger):
        raise ValueError("duplicate virtual candidate ledger item")
    if set(virtual_by_id) != {
        item.candidate_id for item in allocations if item.selected
    }:
        raise ValueError("virtual ledger must exactly cover selected candidates")

    effects: list[CandidateAllocationEffect] = []
    for item in sorted(allocations, key=lambda row: row.candidate_id):
        reference = item.reference_quantity if item.selected else 0.0
        selection = reference * item.realized_unit_pnl
        sizing = (item.unconstrained_quantity - reference) * item.realized_unit_pnl
        constraint = (
            item.constrained_quantity - item.unconstrained_quantity
        ) * item.realized_unit_pnl
        discretization = (
            item.discrete_quantity - item.constrained_quantity
        ) * item.realized_unit_pnl
        total = item.discrete_quantity * item.realized_unit_pnl
        effects.append(
            CandidateAllocationEffect(
                candidate_id=item.candidate_id,
                selection_effect=selection,
                sizing_effect=sizing,
                constraint_effect=constraint,
                discretization_effect=discretization,
                total_virtual_pnl=total,
            )
        )

    virtual_pnl = sum(item.realized_virtual_pnl for item in virtual_ledger)
    physical_pnl = sum(item.realized_physical_pnl for item in physical_ledger)
    book_difference = physical_pnl - virtual_pnl
    reasons: set[str] = set()
    if abs(book_difference) > policy.reconciliation_tolerance:
        reasons.add("P9_ATTRIBUTION_DUAL_BOOK_RECONCILIATION_FAILED")
        quality = AttributionQuality.INVALID
    else:
        quality = AttributionQuality.QUALIFIED
    selection_total = sum(item.selection_effect for item in effects)
    sizing_total = sum(item.sizing_effect for item in effects)
    constraint_total = sum(item.constraint_effect for item in effects)
    discretization_total = sum(item.discretization_effect for item in effects)
    netting_effect = physical_pnl - sum(item.total_virtual_pnl for item in effects)
    aggregate = (
        selection_total
        + sizing_total
        + constraint_total
        + discretization_total
        + netting_effect
    )
    payload = {
        "candidate_effects": [item.model_dump(mode="json") for item in effects],
        "selection": selection_total,
        "sizing": sizing_total,
        "constraint": constraint_total,
        "discretization": discretization_total,
        "netting": netting_effect,
        "virtual_pnl": virtual_pnl,
        "physical_pnl": physical_pnl,
        "dual_book_difference": book_difference,
        "quality": quality,
        "reason_codes": sorted(reasons),
    }
    return PortfolioAttributionResult(
        candidate_effects=tuple(effects),
        selection_effect=selection_total,
        sizing_effect=sizing_total,
        constraint_effect=constraint_total,
        discretization_effect=discretization_total,
        netting_diversification_effect=netting_effect,
        virtual_pnl=virtual_pnl,
        physical_pnl=physical_pnl,
        dual_book_difference=book_difference,
        aggregate_pnl_effect=aggregate,
        quality=quality,
        reason_codes=tuple(sorted(reasons)),
        result_sha256=payload_sha256(payload),
    )
