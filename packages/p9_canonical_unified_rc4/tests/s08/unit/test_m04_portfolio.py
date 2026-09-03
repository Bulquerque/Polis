import pytest

from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality
from quant_pipeline.phase_09.subphases.s08_attribution.m04_portfolio_attribution import CandidateAllocationRecord, PhysicalPositionLedgerItem, PortfolioAttributionPolicy, VirtualCandidateLedgerItem, attribute_portfolio_construction


def _allocation(**updates):
    base=dict(candidate_id="a", selected=True, ranking_position=1, realized_unit_pnl=2.0, reference_quantity=1.0, unconstrained_quantity=2.0, constrained_quantity=1.5, discrete_quantity=1.0)
    base.update(updates)
    return CandidateAllocationRecord(**base)


def test_sequential_portfolio_effects():
    allocation=_allocation()
    virtual=(VirtualCandidateLedgerItem(candidate_id="a", discrete_quantity=1.0, realized_virtual_pnl=2.0, instrument_quantities=(("x",1.0),)),)
    physical=(PhysicalPositionLedgerItem(instrument_id="x", net_quantity=1.0, realized_physical_pnl=2.0),)
    result=attribute_portfolio_construction((allocation,), virtual, physical, PortfolioAttributionPolicy())
    effect=result.candidate_effects[0]
    assert effect.selection_effect == 2.0
    assert effect.sizing_effect == 2.0
    assert effect.constraint_effect == -1.0
    assert effect.discretization_effect == -1.0
    assert result.aggregate_pnl_effect == 2.0


def test_dual_book_mismatch_is_invalid():
    allocation=_allocation(unconstrained_quantity=1.0, constrained_quantity=1.0)
    virtual=(VirtualCandidateLedgerItem(candidate_id="a", discrete_quantity=1.0, realized_virtual_pnl=2.0, instrument_quantities=(("x",1.0),)),)
    physical=(PhysicalPositionLedgerItem(instrument_id="x", net_quantity=1.0, realized_physical_pnl=3.0),)
    result=attribute_portfolio_construction((allocation,), virtual, physical, PortfolioAttributionPolicy())
    assert result.quality is AttributionQuality.INVALID
    assert "P9_ATTRIBUTION_DUAL_BOOK_RECONCILIATION_FAILED" in result.reason_codes


def test_unselected_candidate_cannot_have_quantity():
    with pytest.raises(ValueError):
        _allocation(selected=False, unconstrained_quantity=1.0)


def test_virtual_ledger_must_cover_selected_candidates():
    with pytest.raises(ValueError):
        attribute_portfolio_construction((_allocation(),), (), (), PortfolioAttributionPolicy())
