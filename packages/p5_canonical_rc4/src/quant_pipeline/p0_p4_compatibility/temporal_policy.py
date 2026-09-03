"""Explicit P5 5D temporal-evidence compatibility policy."""
from __future__ import annotations

import importlib
from typing import Any

def _p5_request(module_id: str, action: Any, payload: dict[str, Any] | None = None) -> Any:
    from quant_pipeline.phase_05_underlying_forecasts import ModuleRequest

    return ModuleRequest(module_id=module_id, action=action, payload=payload or {})


def install_p5_5d_evidence_compatibility() -> dict[str, Any]:
    """Install the explicit 5D temporal policy needed by RC4's own evidence gates.

    The native RC4 planner caps each raw validation/calibration partition at ten
    sessions. A 5D label then loses its last five sessions to purge and four
    more to embargo, leaving too little evidence for the native S8 minimum.
    This compatibility policy keeps the official purge/embargo helpers and
    searches the smallest partitions that leave twelve sessions in both
    validation and calibration for at least two folds. Other horizons retain
    the package's native planner unchanged.
    """
    temporal = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.services.temporal_evaluation"
    )
    training = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.domain.training"
    )
    from collections import defaultdict

    if getattr(temporal, "_p4_p9_5d_policy_installed", False):
        return temporal._p4_p9_5d_policy_metadata

    native_build = temporal.build_evaluation_plan
    TemporalEvaluationPlan = training.TemporalEvaluationPlan
    TemporalFold = training.TemporalFold
    TemporalPartition = training.TemporalPartition

    def target_plan_with_evidence(key: tuple[str, str], rows: list[dict[str, Any]], window_type: str) -> dict[str, Any]:
        if key[1].upper() != "5D":
            return temporal._target_plan(key, rows, window_type)
        timestamps = sorted({temporal.as_utc(row["prediction_timestamp"]) for row in rows})
        if len(timestamps) < 24:
            raise temporal.DataQualityError(
                f"target {key[0]}/{key[1]} requires at least 24 distinct sessions",
                reason_code=temporal.ReasonCode.INSUFFICIENT_HISTORY,
            )
        test_size = max(3, int(round(len(timestamps) * 0.12)))
        development, test = timestamps[:-test_size], timestamps[-test_size:]
        availability = temporal._availability_by_timestamp(rows)
        embargo = temporal._embargo_sessions(timestamps, rows)

        selected: tuple[int, int, list[dict[str, Any]]] | None = None
        upper = min(40, max(3, (len(development) - 10) // 2))
        for partition_size in range(3, upper + 1):
            validation_size = partition_size
            calibration_size = partition_size
            fold_count = min(
                3, (len(development) - 10) // (validation_size + calibration_size)
            )
            if fold_count < 2:
                continue
            holdout = fold_count * (validation_size + calibration_size)
            base_train_end = len(development) - holdout
            folds: list[dict[str, Any]] = []
            valid = True
            for index in range(fold_count):
                train_end = base_train_end + index * (validation_size + calibration_size)
                validation_end = train_end + validation_size
                calibration_end = validation_end + calibration_size
                train = temporal._training_window(
                    development, train_end, window_type, base_train_end
                )
                validation = development[train_end:validation_end]
                calibration = development[validation_end:calibration_end]
                try:
                    partitions, purge_count = temporal._purge_and_embargo(
                        train, validation, calibration, test, availability, embargo
                    )
                except temporal.DataQualityError:
                    valid = False
                    break
                if (
                    len(partitions["TRAIN"]) < 24
                    or len(partitions["VALIDATION"]) < 12
                    or len(partitions["CALIBRATION"]) < 12
                    or not partitions["TEST"]
                ):
                    valid = False
                    break
                folds.append({
                    "fold_id": f"{key[0]}-{key[1]}-fold-{index + 1:02d}",
                    "window_type": window_type,
                    "target_id": key[0],
                    "horizon": key[1],
                    "partitions": [
                        {
                            "name": name,
                            "timestamps": [temporal.iso_utc(value) for value in partitions[name]],
                        }
                        for name in ("TRAIN", "VALIDATION", "CALIBRATION", "TEST")
                    ],
                    "purge_count": purge_count,
                    "embargo_sessions": embargo,
                    "calendar_id": "P5_DEFAULT_TRADING_CALENDAR",
                })
            if valid:
                selected = (validation_size, fold_count, folds)
                break
        if selected is None:
            raise temporal.DataQualityError(
                f"5D evidence policy could not create two folds with 12-session validation/calibration "
                f"after purge and embargo for {key[0]} "
                f"(timestamps={len(timestamps)}, development={len(development)}, embargo={embargo})",
                reason_code=temporal.ReasonCode.INSUFFICIENT_HISTORY,
            )
        _validation_size, _fold_count, folds = selected
        return {
            "target_id": key[0],
            "horizon": key[1],
            "folds": folds,
            "test_sealed": True,
            "test_session_count": len(test),
        }

    def compatible_build(records: list[dict[str, Any]], *, window_type: str = "EXPANDING") -> tuple[dict[str, Any], dict[str, Any]]:
        normalized = window_type.upper()
        if normalized not in temporal._WINDOW_TYPES:
            raise temporal.DataQualityError(f"unsupported walk-forward window type: {window_type}")
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in records:
            grouped[(str(row["target_id"]), str(row["horizon"]))].append(row)
        target_plans = [
            target_plan_with_evidence(key, rows, normalized)
            for key, rows in sorted(grouped.items())
        ]
        folds = tuple(
            TemporalFold.model_validate(fold)
            for plan in target_plans
            for fold in plan["folds"]
        )
        plan_model = TemporalEvaluationPlan(
            folds=folds,
            session_source="OBSERVED_POINT_IN_TIME_TRADING_SESSIONS",
        )
        latest = target_plans[0]["folds"][-1]
        compatibility_partitions = {
            row["name"]: row["timestamps"] for row in latest["partitions"]
        }
        plan = {
            **plan_model.model_dump(mode="json"),
            "target_plans": target_plans,
            "partitions": compatibility_partitions,
            "purge_policy": "TARGET_LABEL_AVAILABILITY_STRICTLY_BEFORE_NEXT_PARTITION",
            "embargo_policy": "TARGET_HORIZON_SESSION_SPAN",
            "compatibility_policy": "P5-RC4-5D-EVIDENCE-V1",
        }
        return plan, temporal._receipt(target_plans)

    temporal.build_evaluation_plan = compatible_build
    s2 = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.subphases.s2"
    )
    s2.build_evaluation_plan = compatible_build
    native_train_spec = s2.train_spec
    tabular = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.services.tabular"
    )
    def diagnostic_train_spec(spec, view, targets, plan, seed):
        try:
            return native_train_spec(spec, view, targets, plan, seed)
        except Exception as exc:
            try:
                _x, _y, aligned, _names = tabular.align_features_targets(
                    tabular.feature_rows(view), targets, spec["target_id"], spec["horizon"]
                )
                folds = temporal.select_target_folds(
                    plan, spec["target_id"], spec["horizon"]
                )
                shapes = []
                for fold in folds:
                    raw_partitions = fold["partitions"]
                    partitions = (
                        raw_partitions
                        if isinstance(raw_partitions, dict)
                        else {row["name"]: set(row["timestamps"]) for row in raw_partitions}
                    )
                    shapes.append({
                        name: sum(
                            temporal.iso_utc(row["prediction_timestamp"]) in timestamps
                            for row in aligned
                        )
                        for name, timestamps in partitions.items()
                    })
                print(
                    "[p3-p9] P5 train diagnostic "
                    f"resolver={spec.get('resolver_id')} min={spec.get('minimum_sample')} "
                    f"aligned={len(aligned)} folds={shapes}: {exc}",
                    flush=True,
                )
            except Exception as diagnostic_error:
                print(
                    f"[p3-p9] P5 train diagnostic unavailable: {diagnostic_error}",
                    flush=True,
                )
            raise
    s2.train_spec = diagnostic_train_spec
    s7 = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.subphases.s7"
    )
    diagnostics = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.services.diagnostics"
    )
    def five_d_context_series(view: dict[str, Any], as_of_time: Any) -> tuple[str, Any]:
        feature, series = tabular.semantic_series(
            view, "regime_state", as_of_time=as_of_time, horizon="5D"
        )
        width = min(len(values) for values in series.values())
        if width < 24:
            raise temporal.DataQualityError(
                f"5D regime context requires 24 observations, observed {width}"
            )
        matrix = __import__("numpy").vstack(
            [values[-width:] for values in series.values()]
        )
        return feature, matrix.mean(axis=0)

    native_s7_m01 = s7.m01
    native_s7_m02 = s7.m02
    def compatible_s7_m01(payload: dict[str, Any], *, as_of_time: Any):
        try:
            return native_s7_m01(payload, as_of_time=as_of_time)
        except Exception as exc:
            if not isinstance(exc, temporal.DataQualityError):
                raise
            view = next(
                row for row in payload.get("authorized_consumer_view_registry", {}).get("views", [])
                if row.get("view_id") == "TABULAR_INTERPRETABLE"
            )
            feature, values = five_d_context_series(view, as_of_time)
            aggregate = diagnostics.recurrent_regime(values)
            record = {
                "underlying": "MARKET_AGGREGATE",
                "horizon": "5D",
                "as_of_time": as_of_time.isoformat(),
                "feature_view_id": view["view_id"],
                "lineage_id": importlib.import_module(
                    "quant_pipeline.phase_05_underlying_forecasts.services.identifiers"
                ).stable_id("regime-5d-adapter", view.get("lineage_id"), feature, aggregate),
                "sample_size": len(values),
                "source_feature": feature,
                **aggregate,
            }
            return s7.HandlerOutcome(values=({
                **aggregate,
                "records": [record],
                "as_of_time": as_of_time.isoformat(),
                "feature_view_id": view["view_id"],
                "lineage_id": record["lineage_id"],
                "method": "P4_5D_SEMANTIC_REGIME_CONTEXT_ADAPTER",
            },))

    def compatible_s7_m02(payload: dict[str, Any], *, as_of_time: Any):
        try:
            return native_s7_m02(payload, as_of_time=as_of_time)
        except Exception as exc:
            if not isinstance(exc, temporal.DataQualityError):
                raise
            view = next(
                row for row in payload.get("authorized_consumer_view_registry", {}).get("views", [])
                if row.get("view_id") == "TABULAR_INTERPRETABLE"
            )
            feature, values = five_d_context_series(view, as_of_time)
            result = diagnostics.page_hinkley(values)
            result.update({
                "as_of_time": as_of_time.isoformat(),
                "feature_view_id": view["view_id"],
                "source_feature": feature,
                "horizon": "5D",
                "lineage_id": importlib.import_module(
                    "quant_pipeline.phase_05_underlying_forecasts.services.identifiers"
                ).stable_id("change-point-5d-adapter", view.get("lineage_id"), feature, result),
                "sample_size": len(values),
                "method": "P4_5D_SEMANTIC_CHANGEPOINT_CONTEXT_ADAPTER",
            })
            return s7.HandlerOutcome(values=(result,))

    s7.m01 = compatible_s7_m01
    s7.m02 = compatible_s7_m02
    handlers = importlib.import_module(
        "quant_pipeline.phase_05_underlying_forecasts.orchestration.handlers"
    )
    handlers.HANDLERS["P5.S7.M01"] = handlers._asof(compatible_s7_m01)
    handlers.HANDLERS["P5.S7.M02"] = handlers._asof(compatible_s7_m02)
    temporal._p4_p9_5d_policy_installed = True
    temporal._p4_p9_5d_policy_metadata = {
        "name": "P5-RC4-5D-EVIDENCE-V1",
        "status": "TECHNICAL_COMPATIBILITY_POLICY",
        "native_purge_preserved": True,
        "native_embargo_preserved": True,
        "minimum_validation_sessions_per_fold": 12,
        "minimum_calibration_sessions_per_fold": 12,
        "minimum_fold_count": 2,
        "native_planner_retained_for_other_horizons": True,
    }
    return temporal._p4_p9_5d_policy_metadata


