class S20Error(Exception):
    """Base error for P3.S20."""

class S20ContractError(S20Error):
    pass

class S20TemporalError(S20Error):
    pass

class S20LineageError(S20Error):
    pass

class S20ProviderError(S20Error):
    pass

class S20BudgetError(S20Error):
    pass
