"""Immutable policy objects injected into S1 modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ContractCompatibilityPolicy:
    accepted_contract_versions: frozenset[str] = frozenset({"P7_TO_P8_RANKING_HANDOFF_V1"})
    accepted_schema_versions: frozenset[str] = frozenset({"1.0.0"})
    accepted_producer_phases: frozenset[str] = frozenset({"P7"})
    forbidden_fields: frozenset[str] = frozenset(
        {
            "portfolio_weight",
            "final_position_size",
            "execution_price",
            "future_return",
            "realized_pnl",
            "manual_trade",
            "current_cycle_override",
            "guaranteed_return",
        }
    )

    def __post_init__(self) -> None:
        if not self.accepted_contract_versions or not self.accepted_schema_versions:
            raise ValueError("accepted contract/schema versions must not be empty")


@dataclass(frozen=True, slots=True)
class ReferenceResolutionPolicy:
    full_lineage_resolution: bool = True
    require_ranked_candidate_evidence: bool = True


@dataclass(frozen=True, slots=True)
class StateReconciliationPolicy:
    position_quantity_tolerance: Decimal = Decimal("0")
    cash_tolerance: Decimal = Decimal("0.01")
    margin_tolerance: Decimal = Decimal("0.01")
    collateral_tolerance: Decimal = Decimal("0.01")
    open_order_quantity_tolerance: Decimal = Decimal("0")
    material_discrepancy_limit: int = 0

    def __post_init__(self) -> None:
        values = (
            self.position_quantity_tolerance,
            self.cash_tolerance,
            self.margin_tolerance,
            self.collateral_tolerance,
            self.open_order_quantity_tolerance,
        )
        if any(value < 0 for value in values):
            raise ValueError("reconciliation tolerances must be non-negative")
        if self.material_discrepancy_limit < 0:
            raise ValueError("material_discrepancy_limit must be non-negative")


@dataclass(frozen=True, slots=True)
class S1Policy:
    compatibility: ContractCompatibilityPolicy = field(default_factory=ContractCompatibilityPolicy)
    reference_resolution: ReferenceResolutionPolicy = field(default_factory=ReferenceResolutionPolicy)
    state_reconciliation: StateReconciliationPolicy = field(default_factory=StateReconciliationPolicy)
