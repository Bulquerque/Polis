from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ..economic_errors import ContractError
from ..feature_records import one_record
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec, QualityState
from ..provenance import Provenance, ProvenanceIndex, combine_quality, is_usable
from .option_math import implied_volatility

MODULE_ID = "P4.S4.M05"
SUPPORTED_OBSERVERS = {
    "options.coverage_count",
    "options.atm_implied_volatility",
    "options.put_call_volume_ratio",
    "options.put_call_open_interest_ratio",
    "options.open_interest_concentration",
    "options.implied_volatility_term_slope",
    "options.implied_volatility_skew_proxy",
    "options.variance_risk_premium",
}
OPTION_VARIABLES = {
    "option.bid",
    "option.ask",
    "option.last_price",
    "option.volume",
    "option.open_interest",
    "option.implied_volatility",
    "option.risk_free_rate",
    "option.dividend_yield",
}


def _numeric(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return np.nan
    result = float(value)
    return result if np.isfinite(result) else np.nan


def _contract_frame(observations: tuple[CanonicalObservation, ...]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in observations:
        if row.variable_id not in OPTION_VARIABLES or not is_usable(row):
            continue
        underlying_id = str(row.attributes.get("underlying_id", ""))
        if not underlying_id:
            continue
        rows.append(
            {
                "decision_time": row.decision_time,
                "contract_key": str(row.attributes.get("contract_key", row.entity_id)),
                "variable_id": row.variable_id,
                "value": _numeric(row.value),
                "available_at": row.available_at,
                "record_lineage_id": row.record_lineage_id,
                "source_modality": row.source_modality,
                "quality_state": row.quality_state,
                "underlying_id": underlying_id,
                "expiration_date": row.attributes.get("expiration_date"),
                "strike": row.attributes.get("strike"),
                "option_type": str(row.attributes.get("option_type", "")).upper(),
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    duplicated = frame.duplicated(["decision_time", "contract_key", "variable_id"], keep=False)
    if duplicated.any():
        sample = frame.loc[duplicated, ["decision_time", "contract_key", "variable_id"]].head(20).to_dict("records")
        raise ContractError("P4_S4_M05_DUPLICATE_OPTION_OBSERVATION", "duplicate option observations", details={"sample": sample})
    metadata = frame.groupby(["decision_time", "contract_key"], sort=True).agg(
        available_at=("available_at", "max"),
        lineages=("record_lineage_id", lambda values: tuple(sorted(set(values)))),
        modalities=("source_modality", lambda values: tuple(sorted(set(values)))),
        quality_states=("quality_state", lambda values: tuple(values)),
        underlying_id=("underlying_id", "first"),
        expiration_date=("expiration_date", "first"),
        strike=("strike", "first"),
        option_type=("option_type", "first"),
    )
    values = frame.pivot(index=["decision_time", "contract_key"], columns="variable_id", values="value")
    return metadata.join(values).reset_index()


def _spot_frame(observations: tuple[CanonicalObservation, ...]) -> pd.DataFrame:
    rows = [
        {
            "decision_time": row.decision_time,
            "underlying_id": row.entity_id,
            "spot": _numeric(row.value),
            "spot_available_at": row.available_at,
            "spot_lineages": (row.record_lineage_id,),
            "spot_modalities": (row.source_modality,),
            "spot_quality": row.quality_state,
        }
        for row in observations
        if row.variable_id == "market.close" and is_usable(row)
    ]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if frame.duplicated(["decision_time", "underlying_id"], keep=False).any():
        raise ContractError("P4_S4_M05_DUPLICATE_SPOT", "duplicate spot observations for options aggregation")
    return frame


def _add_implied_volatility(frame: pd.DataFrame, specs: tuple[ObserverSpec, ...]) -> pd.DataFrame:
    allow_solver = any(spec.parameters.get("allow_iv_solver") is True for spec in specs)
    iv_values: list[float | None] = []
    methods: list[str] = []
    for row in frame.to_dict("records"):
        provided = row.get("option.implied_volatility")
        if provided is not None and not pd.isna(provided) and float(provided) > 0:
            iv_values.append(float(provided))
            methods.append("PROVIDER_IV")
            continue
        if not allow_solver:
            iv_values.append(None)
            methods.append("UNAVAILABLE_SOLVER_NOT_AUTHORIZED")
            continue
        bid, ask, last = row.get("option.bid"), row.get("option.ask"), row.get("option.last_price")
        mid: float | None = None
        if bid is not None and ask is not None and not pd.isna(bid) and not pd.isna(ask) and ask >= bid >= 0:
            mid = (float(bid) + float(ask)) / 2.0
        elif last is not None and not pd.isna(last) and float(last) > 0:
            mid = float(last)
        expiry = pd.to_datetime(row.get("expiration_date"), utc=True, errors="coerce")
        decision = pd.to_datetime(row.get("decision_time"), utc=True)
        time_to_expiry = (expiry - decision).total_seconds() / (365.25 * 24 * 3600) if not pd.isna(expiry) else -1
        spot, strike = row.get("spot"), row.get("strike")
        rate, dividend = row.get("option.risk_free_rate"), row.get("option.dividend_yield")
        if any(value is None or pd.isna(value) for value in (mid, spot, strike)) or time_to_expiry <= 0:
            iv_values.append(None)
            methods.append("UNAVAILABLE_INCOMPLETE_QUOTE")
            continue
        if rate is None or dividend is None or pd.isna(rate) or pd.isna(dividend):
            iv_values.append(None)
            methods.append("UNAVAILABLE_MISSING_CARRY_INPUTS")
            continue
        option_type = str(row.get("option_type", "")).upper()
        if option_type not in {"C", "P"}:
            iv_values.append(None)
            methods.append("UNAVAILABLE_INVALID_OPTION_TYPE")
            continue
        iv = implied_volatility(
            price=float(mid),
            spot=float(spot),
            strike=float(strike),
            time_to_expiry=float(time_to_expiry),
            rate=float(rate),
            dividend_yield=float(dividend),
            option_type=option_type,
        )
        iv_values.append(iv)
        methods.append("DETERMINISTIC_IV_SOLVER" if iv is not None else "UNAVAILABLE_NO_BRACKETED_ROOT")
    result = frame.copy()
    result["computed_iv"] = iv_values
    result["iv_method"] = methods
    return result


def _realized_volatility(observations: tuple[CanonicalObservation, ...], window: int = 21) -> pd.DataFrame:
    rows = [
        {"decision_time": row.decision_time, "underlying_id": row.entity_id, "close": _numeric(row.value)}
        for row in observations
        if row.variable_id == "market.close" and is_usable(row)
    ]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).sort_values(["underlying_id", "decision_time"])
    frame["return"] = frame.groupby("underlying_id", sort=False)["close"].pct_change(fill_method=None)
    frame["realized_volatility"] = frame.groupby("underlying_id", sort=False)["return"].transform(
        lambda series: series.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(252.0)
    )
    provenance_index = ProvenanceIndex(observations)
    provenances = [
        provenance_index.collect(
            entity_id=str(row.underlying_id),
            decision_time=row.decision_time,
            requirements={"market.close": window + 1},
        )
        for row in frame.itertuples(index=False)
    ]
    frame["rv_available_at"] = [item.available_at if item else pd.NaT for item in provenances]
    frame["rv_lineages"] = [item.lineage_ids if item else () for item in provenances]
    frame["rv_modalities"] = [item.modalities if item else () for item in provenances]
    frame["rv_quality"] = [item.quality_state if item else QualityState.DEGRADED for item in provenances]
    return frame[
        [
            "decision_time",
            "underlying_id",
            "realized_volatility",
            "rv_available_at",
            "rv_lineages",
            "rv_modalities",
            "rv_quality",
        ]
    ]


def _aggregate(group: pd.DataFrame, observer_id: str, realized_volatility: float | None) -> tuple[float | None, str, dict[str, Any]]:
    if observer_id == "options.coverage_count":
        return float(len(group)), "contracts", {}
    if observer_id == "options.atm_implied_volatility":
        valid = group.dropna(subset=["computed_iv", "spot", "strike"]).copy()
        if valid.empty:
            methods = tuple(sorted(set(group["iv_method"])))
            return None, "annualized_volatility", {"method": methods[0] if len(methods) == 1 else "MIXED_UNAVAILABLE"}
        valid["distance"] = np.abs(np.log(valid["strike"].astype(float) / valid["spot"].astype(float)))
        best = valid.sort_values(["distance", "contract_key"]).iloc[0]
        return float(best["computed_iv"]), "annualized_volatility", {"method": best["iv_method"]}
    if observer_id in {"options.put_call_volume_ratio", "options.put_call_open_interest_ratio"}:
        column = "option.volume" if observer_id.endswith("volume_ratio") else "option.open_interest"
        if column not in group:
            return None, "ratio", {"put_observation_count": 0, "call_observation_count": 0}
        puts = group.loc[group["option_type"].eq("P"), column].dropna()
        calls = group.loc[group["option_type"].eq("C"), column].dropna()
        put_total, call_total = float(puts.sum()), float(calls.sum())
        value = put_total / call_total if not puts.empty and not calls.empty and call_total > 0 else None
        return value, "ratio", {
            "put_total": put_total,
            "call_total": call_total,
            "put_observation_count": len(puts),
            "call_observation_count": len(calls),
        }
    if observer_id == "options.open_interest_concentration":
        if "option.open_interest" not in group:
            return None, "hhi", {"open_interest_total": 0.0}
        values = group["option.open_interest"].dropna()
        if values.empty or (values < 0).any():
            return None, "hhi", {"open_interest_total": 0.0}
        total = float(values.sum())
        return (float(((values / total) ** 2).sum()) if total > 0 else None), "hhi", {"open_interest_total": total}
    valid = group.dropna(subset=["computed_iv", "spot", "strike"]).copy()
    if observer_id == "options.implied_volatility_term_slope":
        if valid.empty:
            return None, "annualized_volatility_difference", {}
        valid["expiry"] = pd.to_datetime(valid["expiration_date"], utc=True, errors="coerce")
        by_expiry = valid.groupby("expiry")["computed_iv"].median().dropna().sort_index()
        value = float(by_expiry.iloc[-1] - by_expiry.iloc[0]) if len(by_expiry) >= 2 else None
        return value, "annualized_volatility_difference", {"maturity_count": len(by_expiry)}
    if observer_id == "options.implied_volatility_skew_proxy":
        if valid.empty:
            return None, "annualized_volatility_difference", {"method": "MONEYNESS_BUCKET_PROXY"}
        valid["moneyness"] = valid["strike"].astype(float) / valid["spot"].astype(float)
        puts = valid[valid["option_type"].eq("P") & valid["moneyness"].between(0.85, 1.0)]["computed_iv"]
        calls = valid[valid["option_type"].eq("C") & valid["moneyness"].between(1.0, 1.15)]["computed_iv"]
        value = float(puts.median() - calls.median()) if not puts.empty and not calls.empty else None
        return value, "annualized_volatility_difference", {"method": "MONEYNESS_BUCKET_PROXY"}
    if observer_id == "options.variance_risk_premium":
        atm, _, attributes = _aggregate(group, "options.atm_implied_volatility", realized_volatility)
        if atm is None or realized_volatility is None or pd.isna(realized_volatility):
            return None, "annualized_variance_difference", attributes
        return float(atm**2 - float(realized_volatility) ** 2), "annualized_variance_difference", attributes
    raise KeyError(observer_id)


def _provenance(group: pd.DataFrame, observer_id: str) -> Provenance:
    lineages = [item for values in group["lineages"] for item in values]
    modalities = [item for values in group["modalities"] for item in values]
    available = list(group["available_at"])
    quality_states = [item for values in group["quality_states"] for item in values]
    if observer_id not in {
        "options.coverage_count",
        "options.put_call_volume_ratio",
        "options.put_call_open_interest_ratio",
        "options.open_interest_concentration",
    }:
        lineages.extend(item for values in group["spot_lineages"] for item in values)
        modalities.extend(item for values in group["spot_modalities"] for item in values)
        available.extend(group["spot_available_at"].dropna())
        quality_states.extend(group["spot_quality"])
    if observer_id == "options.variance_risk_premium" and "rv_lineages" in group:
        lineages.extend(item for values in group["rv_lineages"] for item in values)
        modalities.extend(item for values in group["rv_modalities"] for item in values)
        available.extend(group["rv_available_at"].dropna())
        quality_states.extend(group["rv_quality"])
    return Provenance(
        available_at=max(available),
        lineage_ids=tuple(sorted(set(lineages))),
        modalities=tuple(sorted(set(modalities))),
        quality_state=combine_quality(quality_states),
    )


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    contracts = _contract_frame(observations)
    spots = _spot_frame(observations)
    if contracts.empty or spots.empty:
        return []
    frame = contracts.merge(spots, on=["decision_time", "underlying_id"], how="left")
    frame = _add_implied_volatility(frame, specs)
    realized = _realized_volatility(observations)
    if not realized.empty:
        frame = frame.merge(realized, on=["decision_time", "underlying_id"], how="left")
    output: list[AtomicFeatureRecord] = []
    for (decision_time, underlying_id), group in frame.groupby(["decision_time", "underlying_id"], sort=True):
        rv = group["realized_volatility"].iloc[0] if "realized_volatility" in group else None
        for spec in specs:
            value, unit, attributes = _aggregate(group, spec.observer_id, rv)
            provenance = _provenance(group, spec.observer_id)
            output.append(
                one_record(
                    decision_time=decision_time.to_pydatetime() if hasattr(decision_time, "to_pydatetime") else decision_time,
                    entity_id=str(underlying_id),
                    spec=spec,
                    value=value,
                    unit=unit,
                    available_at=provenance.available_at,
                    lineage_ids=provenance.lineage_ids,
                    modalities=provenance.modalities,
                    quality_state=provenance.quality_state,
                    attributes={**attributes, "contract_count": len(group)},
                )
            )
    return output
