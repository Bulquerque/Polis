from ..domain.constraint_compilation import compile_constraints
from ..models.artifacts import CompiledConstraintSet
from ..models.inputs import DecisionReadyRiskPayload

MODULE_ID = "P8.S5.M02"


def run_module(payload: DecisionReadyRiskPayload) -> CompiledConstraintSet:
    return compile_constraints(payload)
