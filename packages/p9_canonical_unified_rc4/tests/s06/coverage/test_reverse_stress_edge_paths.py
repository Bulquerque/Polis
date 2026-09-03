from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from quant_pipeline.phase_09.subphases.s06_structural_stress import (
    m07_reverse_stress_breakpoint_and_resilience_engine as engine,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    BreachDirection,
    OutputSemantics,
    S6State,
    SeedPolicy,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    FactorBound,
    FailureCondition,
    QuadraticResponseModel,
    ReverseStressRequest,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import ReverseStressPolicy


def _request(context, *, baseline: float = 0.0, minimum_safe_distance: float = 0.5):
    model = QuadraticResponseModel(
        model_id="edge-linear",
        factor_ids=("x",),
        units=("unit",),
        baseline_value=baseline,
        linear_coefficients=(-1.0,),
        quadratic_matrix=((0.0,),),
        semantics=OutputSemantics.PNL,
        model_sha256=content_sha256({"baseline": baseline, "linear": -1.0}),
    )
    return ReverseStressRequest(
        context=context,
        response_model=model,
        bounds=(FactorBound(factor_id="x", lower=-2.0, upper=2.0),),
        failure_condition=FailureCondition(
            condition_id="limit",
            threshold=-1.0,
            breach_direction=BreachDirection.LESS_THAN_OR_EQUAL,
        ),
        seed_policy=SeedPolicy(root_entropy=91),
        policy=ReverseStressPolicy(minimum_safe_distance=minimum_safe_distance),
    )


def test_baseline_failure_is_structurally_unsafe(context):
    result = engine.solve_reverse_stress(_request(context, baseline=-2.0))
    assert result.status is S6State.STRUCTURALLY_UNSAFE
    assert result.distance_to_failure == 0.0


def test_near_breakpoint_is_flagged(context):
    result = engine.solve_reverse_stress(
        _request(context, minimum_safe_distance=1.5)
    )
    assert result.status is S6State.REVERSE_STRESS_TOO_CLOSE


def test_forward_verification_failure_is_limited(context, monkeypatch):
    request = _request(context)

    def fake_candidates(*_args, **_kwargs):
        return [(np.asarray([2.0], dtype=np.float64), -2.0)], ["synthetic"]

    monkeypatch.setattr(engine, "_optimize_candidates", fake_candidates)
    result = engine.solve_reverse_stress(request)
    assert result.status is S6State.RESILIENT_WITH_LIMITATIONS
    assert "P9_STRESS_REVERSE_FORWARD_VERIFICATION_FAILED" in result.reason_codes


def test_nonconverged_search_with_corner_failure_is_explicit(context, monkeypatch):
    request = _request(context)
    monkeypatch.setattr(engine, "_optimize_candidates", lambda *_args: ([], ["failed"]))
    result = engine.solve_reverse_stress(request)
    assert result.status is S6State.SEARCH_NOT_CONVERGED
    assert "P9_STRESS_REVERSE_SEARCH_NOT_CONVERGED" in result.reason_codes


def test_large_domain_probe_uses_axis_endpoints():
    lower = np.full(13, -1.0, dtype=np.float64)
    upper = np.full(13, 1.0, dtype=np.float64)
    vectors = engine._domain_probe_vectors(lower, upper)
    assert len(vectors) == 26
    assert all(np.count_nonzero(vector) == 1 for vector in vectors)
