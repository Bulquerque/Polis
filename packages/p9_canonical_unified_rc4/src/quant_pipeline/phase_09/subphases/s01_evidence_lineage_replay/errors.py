class P9S1Error(RuntimeError):
    """Base error for unrecoverable P9.S1 execution failures."""


class ContractError(P9S1Error):
    pass


class IntegrityError(P9S1Error):
    pass


class LineageIntegrityError(P9S1Error):
    pass


class ReplayError(P9S1Error):
    pass
