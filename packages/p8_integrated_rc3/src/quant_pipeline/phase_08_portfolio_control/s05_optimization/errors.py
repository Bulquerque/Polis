class P8S5Error(Exception):
    """Base error for P8.S5."""


class IntegrityError(P8S5Error):
    pass


class ContractIntegrityError(IntegrityError):
    pass


class HashMismatchError(IntegrityError):
    pass


class ObjectiveSemanticError(P8S5Error):
    pass


class ForbiddenOrdinalUseError(ObjectiveSemanticError):
    pass


class ConstraintSemanticError(P8S5Error):
    pass


class ContradictoryConstraintError(ConstraintSemanticError):
    pass


class SolverAdapterError(P8S5Error):
    pass


class SolutionRevalidationError(P8S5Error):
    pass


class NumericalStabilityError(P8S5Error):
    pass


class DiscreteRepairFailedError(P8S5Error):
    pass
