from ..domain.objective_compilation import compile_objective
from ..models.artifacts import CompiledPortfolioObjective
from ..models.inputs import DecisionReadyRiskPayload

MODULE_ID = "P8.S5.M01"


def run_module(payload: DecisionReadyRiskPayload) -> CompiledPortfolioObjective:
    return compile_objective(payload)
