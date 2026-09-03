"""Canonical handler dispatch for the 45 module IDs."""
from __future__ import annotations

from typing import Any, Callable

from ..context import P5ExecutionContext
from ..domain.core import HandlerOutcome, ModuleRequest
from ..subphases import s1, s2, s3, s4, s5, s6, s7, s8, s9

Handler = Callable[[dict[str, Any], ModuleRequest, P5ExecutionContext], HandlerOutcome]


def _simple(function):
    return lambda payload, request, context: function(payload)


def _asof(function):
    return lambda payload, request, context: function(payload, as_of_time=context.as_of_time)


def _seeded(function):
    return lambda payload, request, context: function(payload, as_of_time=context.as_of_time, seed=context.seed)


def _s1_m01(payload, request, context):
    return s1.m01(
        payload, context_as_of_time=context.as_of_time,
        context_generated_at=context.generated_at, expected_cycle_id=context.cycle_id,
        expected_run_id=context.run_id,
    )


def _s1_m04(payload, request, context):
    return s1.m04(
        payload, current_cycle_id=context.cycle_id, current_as_of_time=context.as_of_time
    )


def _s1_m05(payload, request, context):
    return s1.m05(
        payload, run_id=context.run_id, cycle_id=context.cycle_id,
        as_of_time=context.as_of_time, created_at=context.generated_at,
    )


def _s2_m04(payload, request, context):
    return s2.m04(payload, seed=context.seed)


def _s3(module_id):
    return lambda payload, request, context: s3.run(module_id, payload, as_of_time=context.as_of_time)


def _s9_m02(payload, request, context):
    return s9.m02(
        payload, run_id=context.run_id, cycle_id=context.cycle_id,
        decision_time=context.generated_at.isoformat(),
        created_at=context.generated_at.isoformat(),
    )


def _s9_m03(payload, request, context):
    return s9.m03(
        payload, run_id=context.run_id, cycle_id=context.cycle_id,
        decision_time=context.generated_at.isoformat(), created_at=context.generated_at.isoformat(),
    )


def _s9_m05(payload, request, context):
    return s9.m05(
        payload, run_id=context.run_id, cycle_id=context.cycle_id,
        decision_time=context.generated_at.isoformat(), created_at=context.generated_at.isoformat(),
        output_references=payload.get("__input_references__", {}),
    )


HANDLERS: dict[str, Handler] = {
    "P5.S1.M01": _s1_m01,
    "P5.S1.M02": _simple(s1.m02),
    "P5.S1.M03": _simple(s1.m03),
    "P5.S1.M04": _s1_m04,
    "P5.S1.M05": _s1_m05,
    "P5.S2.M01": _asof(s2.m01),
    "P5.S2.M02": _simple(s2.m02),
    "P5.S2.M03": _simple(s2.m03),
    "P5.S2.M04": _s2_m04,
    "P5.S2.M05": _simple(s2.m05),
    "P5.S3.M01": _s3("P5.S3.M01"),
    "P5.S3.M02": _s3("P5.S3.M02"),
    "P5.S3.M03": _s3("P5.S3.M03"),
    "P5.S3.M04": _s3("P5.S3.M04"),
    "P5.S3.M05": _s3("P5.S3.M05"),
    "P5.S4.M01": _asof(s4.m01),
    "P5.S4.M02": _asof(s4.m02),
    "P5.S4.M03": _asof(s4.m03),
    "P5.S4.M04": _asof(s4.m04),
    "P5.S4.M05": _asof(s4.m05),
    "P5.S5.M01": _asof(s5.m01),
    "P5.S5.M02": _asof(s5.m02),
    "P5.S5.M03": _asof(s5.m03),
    "P5.S5.M04": _seeded(s5.m04),
    "P5.S5.M05": _seeded(s5.m05),
    "P5.S5.M06": _simple(s5.m06),
    "P5.S6.M01": _asof(s6.m01),
    "P5.S6.M02": _asof(s6.m02),
    "P5.S6.M03": _asof(s6.m03),
    "P5.S6.M04": _simple(s6.m04),
    "P5.S7.M01": _asof(s7.m01),
    "P5.S7.M02": _asof(s7.m02),
    "P5.S7.M03": _asof(s7.m03),
    "P5.S7.M04": _simple(s7.m04),
    "P5.S7.M05": _simple(s7.m05),
    "P5.S8.M01": _simple(s8.m01),
    "P5.S8.M02": _simple(s8.m02),
    "P5.S8.M03": _simple(s8.m03),
    "P5.S8.M04": _simple(s8.m04),
    "P5.S8.M05": _simple(s8.m05),
    "P5.S9.M01": _simple(s9.m01),
    "P5.S9.M02": _s9_m02,
    "P5.S9.M03": _s9_m03,
    "P5.S9.M04": _simple(s9.m04),
    "P5.S9.M05": _s9_m05,
}
