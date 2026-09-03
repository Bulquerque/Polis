from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.foundation.enums import SecurityType
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256, deterministic_id

from .accounting_models import (
    BorrowFeeEvent,
    CashAdjustmentEvent,
    CashLedgerEntry,
    CollateralLedgerEntry,
    CollateralTransferEvent,
    CostLedgerEntry,
    FeeEvent,
    JournalEntry,
    JournalPosting,
    MarginChangeEvent,
    MarginLedgerEntry,
    PremiumLedgerEntry,
    RealizedPnLEntry,
)
from .enums import AccountCode, CashAdjustmentType, JournalSide, PositionTransitionType, StatefulEventKind
from .errors import AccountingIntegrityError
from .input_models import S8InputBundle
from .registry import instrument_registry
from .state_models import AccountingBundle, CurrencyAccountStateFinal, PositionLifecycleBundle
from .timeline_models import OrderedEventQueue

MODULE_ID = "P8.S8.M04"


def _posting(entry_id, index, event_time, currency, account, amount, instrument=None):
    if amount == 0:
        return None
    side = JournalSide.DEBIT if amount > 0 else JournalSide.CREDIT
    return JournalPosting(
        posting_id=deterministic_id("posting", entry_id, index),
        entry_id=entry_id,
        event_time=event_time,
        currency=currency,
        account_code=account,
        side=side,
        amount=abs(amount),
        instrument_id=instrument,
    )


def _journal(source_id, event_time, description, currency, signed_postings):
    entry_id = deterministic_id("journal", source_id, description)
    postings = tuple(
        item for index, (account, amount, instrument) in enumerate(signed_postings)
        if (item := _posting(entry_id, index, event_time, currency, account, amount, instrument)) is not None
    )
    return JournalEntry(
        entry_id=entry_id,
        source_event_id=source_id,
        event_time=event_time,
        description=description,
        postings=postings,
    )


def _position_account(security_type: SecurityType, before: Decimal, after: Decimal) -> AccountCode:
    if security_type == SecurityType.OPTION:
        return AccountCode.OPTION_PREMIUM_BASIS
    if before < 0 or after < 0:
        return AccountCode.SHORT_POSITION_BASIS
    return AccountCode.LONG_POSITION_BASIS


def _apply_cash(accounts, currency, delta, event_id, event_time, category, cash_ledger):
    account = accounts.get(currency)
    if account is None:
        account = {"cash": Decimal("0"), "collateral": Decimal("0"), "liabilities": Decimal("0"), "margin": Decimal("0")}
        accounts[currency] = account
    account["cash"] += delta
    cash_ledger.append(
        CashLedgerEntry(
            event_id=event_id,
            event_time=event_time,
            currency=currency,
            delta=delta,
            balance_after=account["cash"],
            category=category,
        )
    )


def _transition_entries(value, positions, accounts, journals, cash_ledger, premium_ledger, realized_ledger):
    instruments = instrument_registry(value)
    for transition in positions.transitions:
        if transition.candidate_id is not None or transition.transition_type in {
            PositionTransitionType.REALLOCATION,
            PositionTransitionType.CORPORATE_ACTION,
        }:
            continue
        spec = instruments[transition.instrument_id]
        basis_delta = transition.signed_cost_basis_after - transition.signed_cost_basis_before
        signed = [
            (AccountCode.CASH_AVAILABLE, transition.cash_trade_delta, transition.instrument_id),
            (_position_account(spec.security_type, transition.quantity_before, transition.quantity_after), basis_delta, transition.instrument_id),
            (AccountCode.REALIZED_PNL, -transition.realized_pnl_delta, transition.instrument_id),
        ]
        journals.append(
            _journal(
                transition.source_event_id,
                transition.event_time,
                "POSITION_TRANSITION",
                transition.currency,
                signed,
            )
        )
        if transition.cash_trade_delta:
            _apply_cash(
                accounts, transition.currency, transition.cash_trade_delta,
                transition.source_event_id, transition.event_time,
                "TRADE_OR_SETTLEMENT", cash_ledger,
            )
        if spec.security_type == SecurityType.OPTION and transition.cash_trade_delta:
            premium_ledger.append(
                PremiumLedgerEntry(
                    event_id=transition.source_event_id,
                    event_time=transition.event_time,
                    instrument_id=transition.instrument_id,
                    currency=transition.currency,
                    premium_cash_delta=transition.cash_trade_delta,
                )
            )
        if transition.realized_pnl_delta:
            realized_ledger.append(
                RealizedPnLEntry(
                    event_id=transition.source_event_id,
                    event_time=transition.event_time,
                    instrument_id=transition.instrument_id,
                    currency=transition.currency,
                    amount=transition.realized_pnl_delta,
                )
            )


def _fee_entries(value, registry, accounts, journals, cash_ledger, cost_ledger):
    for fill in value.s7_handoff.s7_result.execution.fill_events:
        if fill.fee == 0:
            continue
        currency = registry[fill.instrument_id].currency
        journals.append(
            _journal(
                fill.fill_id, fill.event_time, "EXECUTION_FEE", currency,
                [
                    (AccountCode.FEES_EXPENSE, fill.fee, fill.instrument_id),
                    (AccountCode.CASH_AVAILABLE, -fill.fee, fill.instrument_id),
                ],
            )
        )
        _apply_cash(accounts, currency, -fill.fee, fill.fill_id, fill.event_time, "FEE", cash_ledger)
        cost_ledger.append(
            CostLedgerEntry(
                event_id=fill.fill_id,
                event_time=fill.event_time,
                currency=currency,
                cost_type="EXECUTION_FEE",
                amount=fill.fee,
            )
        )


def _account_events(queue, accounts, journals, cash_ledger, cost_ledger, margin_ledger, collateral_ledger):
    external_flow = Decimal("0")
    for envelope in queue.events:
        event = envelope.payload
        if envelope.kind == StatefulEventKind.MARGIN_CHANGE and isinstance(event, MarginChangeEvent):
            account = accounts.setdefault(event.currency, {"cash":Decimal("0"),"collateral":Decimal("0"),"liabilities":Decimal("0"),"margin":Decimal("0")})
            account["margin"] = event.new_margin_used
            margin_ledger.append(MarginLedgerEntry(event_id=event.event_id,event_time=event.event_time,currency=event.currency,margin_used_after=event.new_margin_used,reason_code=event.reason_code))
        elif envelope.kind == StatefulEventKind.COLLATERAL_TRANSFER and isinstance(event, CollateralTransferEvent):
            account = accounts.setdefault(event.currency, {"cash":Decimal("0"),"collateral":Decimal("0"),"liabilities":Decimal("0"),"margin":Decimal("0")})
            if account["collateral"] + event.amount_to_restricted < 0:
                raise AccountingIntegrityError("restricted collateral cannot become negative")
            account["collateral"] += event.amount_to_restricted
            journals.append(_journal(event.event_id,event.event_time,"COLLATERAL_TRANSFER",event.currency,[(AccountCode.COLLATERAL_RESTRICTED,event.amount_to_restricted,None),(AccountCode.CASH_AVAILABLE,-event.amount_to_restricted,None)]))
            _apply_cash(accounts,event.currency,-event.amount_to_restricted,event.event_id,event.event_time,"COLLATERAL_TRANSFER",cash_ledger)
            collateral_ledger.append(CollateralLedgerEntry(event_id=event.event_id,event_time=event.event_time,currency=event.currency,available_cash_delta=-event.amount_to_restricted,restricted_collateral_delta=event.amount_to_restricted,restricted_balance_after=account["collateral"]))
        elif envelope.kind == StatefulEventKind.CASH_ADJUSTMENT and isinstance(event, CashAdjustmentEvent):
            is_external=event.adjustment_type in {CashAdjustmentType.DEPOSIT,CashAdjustmentType.WITHDRAWAL,CashAdjustmentType.OTHER}
            offset=AccountCode.EXTERNAL_FLOW_EQUITY if is_external else AccountCode.REALIZED_PNL
            journals.append(_journal(event.event_id,event.event_time,"CASH_ADJUSTMENT",event.currency,[(AccountCode.CASH_AVAILABLE,event.amount,None),(offset,-event.amount,None)]))
            _apply_cash(accounts,event.currency,event.amount,event.event_id,event.event_time,event.adjustment_type.value,cash_ledger)
            if is_external: external_flow += event.amount
        elif envelope.kind == StatefulEventKind.FEE and isinstance(event, FeeEvent):
            journals.append(_journal(event.event_id,event.event_time,"FEE",event.currency,[(AccountCode.FEES_EXPENSE,event.amount,None),(AccountCode.CASH_AVAILABLE,-event.amount,None)]))
            _apply_cash(accounts,event.currency,-event.amount,event.event_id,event.event_time,event.fee_type,cash_ledger)
            cost_ledger.append(CostLedgerEntry(event_id=event.event_id,event_time=event.event_time,currency=event.currency,cost_type=event.fee_type,amount=event.amount))
        elif envelope.kind == StatefulEventKind.BORROW_FEE and isinstance(event, BorrowFeeEvent):
            journals.append(_journal(event.event_id,event.event_time,"BORROW_FEE",event.currency,[(AccountCode.BORROW_EXPENSE,event.amount,None),(AccountCode.CASH_AVAILABLE,-event.amount,None)]))
            _apply_cash(accounts,event.currency,-event.amount,event.event_id,event.event_time,"BORROW_FEE",cash_ledger)
            cost_ledger.append(CostLedgerEntry(event_id=event.event_id,event_time=event.event_time,currency=event.currency,cost_type="BORROW_FEE",amount=event.amount))
    return external_flow


def execute(value: S8InputBundle, queue: OrderedEventQueue, positions: PositionLifecycleBundle) -> AccountingBundle:
    registry = instrument_registry(value)
    accounts = {
        item.currency: {"cash":item.cash_available,"collateral":item.collateral_restricted,"liabilities":item.liabilities,"margin":item.margin_used}
        for item in value.prior_state.accounts
    }
    journals=[]; cash=[]; premium=[]; costs=[]; margins=[]; collateral=[]; realized=[]
    _transition_entries(value,positions,accounts,journals,cash,premium,realized)
    _fee_entries(value,registry,accounts,journals,cash,costs)
    external_flow=_account_events(queue,accounts,journals,cash,costs,margins,collateral)
    final=tuple(CurrencyAccountStateFinal(currency=k,cash_available=v["cash"],collateral_restricted=v["collateral"],liabilities=v["liabilities"],margin_used=v["margin"]) for k,v in sorted(accounts.items()))
    payload={"accounts":final,"journal_entries":tuple(journals),"cash_ledger":tuple(cash),"premium_ledger":tuple(premium),"cost_ledger":tuple(costs),"margin_ledger":tuple(margins),"collateral_ledger":tuple(collateral),"realized_pnl_ledger":tuple(realized),"balanced":True,"external_flow_delta":external_flow}
    return AccountingBundle(**payload,content_sha256=content_sha256(payload))
