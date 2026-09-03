from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.foundation.errors import P8Error


class S8Error(P8Error):
    pass


class TimelineIntegrityError(S8Error):
    pass


class LedgerIntegrityError(S8Error):
    pass


class PositionIntegrityError(S8Error):
    pass


class LifecycleIntegrityError(S8Error):
    pass


class AccountingIntegrityError(S8Error):
    pass


class ValuationIntegrityError(S8Error):
    pass


class ReplayIntegrityError(S8Error):
    pass
