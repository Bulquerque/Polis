from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

import pandas as pd

from quant_pipeline.phase_04_feature_base.models import ExecutionContext
from quant_pipeline.phase_04_feature_base.runtime.canonical import content_hash, p2_legacy_digest

PIPELINE_VERSION = "V14.9-RC1"


def _artifact(name: str, records: list[dict[str, Any]], *, created_at: str, **extra: Any) -> dict[str, Any]:
    return {
        "artifact_id": f"{name}-fixture",
        "created_at": created_at,
        "lineage_id": f"lineage-{name}",
        "pipeline_version": PIPELINE_VERSION,
        "records": records,
        **extra,
    }


def build_full_inputs(periods: int = 90) -> tuple[dict[str, Any], ExecutionContext]:
    dates = pd.bdate_range("2024-01-02", periods=periods, tz="UTC")
    as_of = (dates[-1] + pd.Timedelta(hours=23)).to_pydatetime()
    created = as_of + timedelta(minutes=5)
    context = ExecutionContext.from_mapping(
        {
            "profile": "TEST",
            "run_id": f"run-integrated-{periods}",
            "cycle_id": f"cycle-integrated-{periods}",
            "as_of_time": as_of.isoformat(),
            "decision_time": as_of.isoformat(),
            "created_at": created.isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "contract_generation": PIPELINE_VERSION,
            "architecture_revision": "P4-INTEGRATED-S1-S9-V1",
            "compatibility_mode": "RC4_1",
            "allow_degraded_handoffs": True,
        }
    )

    underlying: list[dict[str, Any]] = []
    benchmark: list[dict[str, Any]] = []
    prices = {"ASSET1": 50.0, "ASSET2": 80.0, "BENCHMARK": 100.0}
    for index, timestamp in enumerate(dates):
        date = timestamp.date().isoformat()
        available_at = (timestamp + pd.Timedelta(hours=20)).isoformat()
        decision_time = (timestamp + pd.Timedelta(hours=21)).isoformat()
        for entity in ("ASSET1", "ASSET2"):
            previous = prices[entity]
            phase = 0.0 if entity == "ASSET1" else 1.0
            prices[entity] *= 1 + 0.0002 + 0.001 * math.sin(2 * math.pi * index / 10 + phase)
            close = prices[entity]
            volume = 120_000 + 15_000 * math.sin(2 * math.pi * index / 10 + phase) + (10_000 if entity == "ASSET1" else 20_000)
            underlying.append(
                {
                    "date": date,
                    "as_of_date": available_at,
                    "available_at": available_at,
                    "decision_time": decision_time,
                    "underlying": entity,
                    "open": previous * 1.0001,
                    "high": max(previous, close) * 1.003,
                    "low": min(previous, close) * 0.997,
                    "close": close,
                    "volume": volume,
                    "financial_volume": volume * close,
                    "bid": close - 0.02,
                    "ask": close + 0.02,
                    "shares_outstanding": 10_000_000,
                    "adjustment_factor": 1.0,
                    "is_trading_day": True,
                    "source_id": "P2",
                    "quality_flag": "PASS",
                    "lineage_id": f"lin-{entity}-{index}",
                    "pipeline_version": PIPELINE_VERSION,
                    "stable_sequence": index * 2 + (0 if entity == "ASSET1" else 1),
                }
            )
        previous = prices["BENCHMARK"]
        prices["BENCHMARK"] *= 1 + 0.00015 + 0.0006 * math.cos(2 * math.pi * index / 10)
        close = prices["BENCHMARK"]
        volume = 500_000 + 40_000 * math.cos(2 * math.pi * index / 10)
        benchmark.append(
            {
                "date": date,
                "as_of_date": available_at,
                "available_at": available_at,
                "decision_time": decision_time,
                "benchmark_id": "BENCHMARK",
                "open": previous,
                "high": max(previous, close) * 1.002,
                "low": min(previous, close) * 0.998,
                "close": close,
                "volume": volume,
                "financial_volume": volume * close,
                "source_id": "P2",
                "quality_flag": "PASS",
                "lineage_id": f"lin-benchmark-{index}",
                "pipeline_version": PIPELINE_VERSION,
                "stable_sequence": index,
            }
        )

    macro_br: list[dict[str, Any]] = []
    macro_us: list[dict[str, Any]] = []
    for sequence, index in enumerate(range(periods)):
        timestamp = dates[index]
        date = timestamp.date().isoformat()
        available_at = (timestamp + pd.Timedelta(hours=12)).isoformat()
        decision_time = (timestamp + pd.Timedelta(hours=21)).isoformat()
        values = (
            ("macro.growth", 100 + 0.8 * math.sin(2 * math.pi * sequence / 10), "index"),
            ("macro.inflation", 4 + 0.2 * math.cos(2 * math.pi * sequence / 10), "percent"),
            ("curve.short_rate", 10 + 0.15 * math.sin(2 * math.pi * sequence / 10), "percent"),
            ("curve.long_rate", 11 + 0.10 * math.cos(2 * math.pi * sequence / 10), "percent"),
            ("futures_basis", 0.25 + 0.02 * math.sin(2 * math.pi * sequence / 10), "percent"),
        )
        for offset, (variable_id, value, unit) in enumerate(values):
            macro_br.append(
                {
                    "date": date,
                    "as_of_date": available_at,
                    "available_at": available_at,
                    "decision_time": decision_time,
                    "entity_id": "BR",
                    "series_id": variable_id,
                    "variable_id": variable_id,
                    "value": value,
                    "unit": unit,
                    "source_id": "P2",
                    "quality_flag": "PASS",
                    "lineage_id": f"lin-br-{variable_id}-{sequence}",
                    "stable_sequence": sequence * 10 + offset,
                }
            )
        macro_us.append(
            {
                "date": date,
                "as_of_date": available_at,
                "available_at": available_at,
                "decision_time": decision_time,
                "entity_id": "US",
                "series_id": "macro.growth",
                "variable_id": "macro.growth",
                "value": 95 + 0.6 * math.sin(2 * math.pi * sequence / 10 + 0.5),
                "unit": "index",
                "source_id": "P2",
                "quality_flag": "PASS",
                "lineage_id": f"lin-us-growth-{sequence}",
                "stable_sequence": sequence,
            }
        )
        event_id = f"macro-release-{sequence}"
        for role, value, suffix in (
            ("EXPECTATION", 100 + 0.3 * math.cos(2 * math.pi * sequence / 10), "expectation"),
            ("ACTUAL", 100 + 0.3 * math.cos(2 * math.pi * sequence / 10) + 0.5 * math.sin(2 * math.pi * sequence / 10), "actual"),
        ):
            macro_br.append(
                {
                    "date": date,
                    "as_of_date": available_at,
                    "available_at": available_at,
                    "decision_time": decision_time,
                    "entity_id": "BR",
                    "series_id": f"macro.release_{suffix}",
                    "variable_id": f"macro.release_{suffix}",
                    "value": value,
                    "unit": "index",
                    "event_id": event_id,
                    "value_role": role,
                    "source_id": "P2",
                    "quality_flag": "PASS",
                    "lineage_id": f"lin-br-release-{suffix}-{sequence}",
                    "stable_sequence": sequence * 100 + (1 if role == "ACTUAL" else 0),
                }
            )

    calendar = [
        {
            "date": timestamp.date().isoformat(),
            "decision_time": (timestamp + pd.Timedelta(hours=21)).isoformat(),
            "is_trading_day": True,
            "available_at": timestamp.isoformat(),
            "lineage_id": f"lin-calendar-{index}",
            "stable_sequence": index,
        }
        for index, timestamp in enumerate(dates)
    ]
    option_contracts: list[dict[str, Any]] = []
    option_quotes: list[dict[str, Any]] = []
    fundamentals: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    curves: list[dict[str, Any]] = []
    for index, timestamp in enumerate(dates):
        date = timestamp.date().isoformat()
        available_at = (timestamp + pd.Timedelta(hours=20)).isoformat()
        decision_time = (timestamp + pd.Timedelta(hours=21)).isoformat()
        for entity in ("ASSET1", "ASSET2"):
            spot = next(
                row["close"]
                for row in underlying
                if row["underlying"] == entity and row["date"] == date
            )
            for expiry_days in (30, 90):
                expiry = (timestamp + pd.Timedelta(days=expiry_days)).date().isoformat()
                for strike_multiplier, option_type in ((0.95, "PUT"), (1.0, "CALL"), (1.05, "CALL")):
                    strike = round(spot * strike_multiplier, 4)
                    contract_key = f"{entity}-{expiry_days}-{strike_multiplier:.2f}-{option_type}"
                    option_contracts.append(
                        {
                            "date": date,
                            "available_at": available_at,
                            "decision_time": decision_time,
                            "underlying": entity,
                            "contract_key": contract_key,
                            "strike": strike,
                            "expiry": expiry,
                            "option_type": option_type,
                            "multiplier": 100,
                            "lineage_id": f"lin-contract-{contract_key}-{index}",
                            "stable_sequence": index * 20 + expiry_days,
                        }
                    )
                    moneyness = abs(strike / spot - 1.0)
                    iv = 0.22 + 0.05 * moneyness + (0.015 if option_type == "PUT" else 0.0) + 0.005 * math.sin(2 * math.pi * index / 10)
                    mid = max(0.10, spot * (0.018 + 0.4 * moneyness) * (expiry_days / 30) ** 0.5)
                    option_quotes.append(
                        {
                            "date": date,
                            "quote_time": available_at,
                            "available_at": available_at,
                            "decision_time": decision_time,
                            "underlying": entity,
                            "contract_key": contract_key,
                            "strike": strike,
                            "expiry": expiry,
                            "option_type": option_type,
                            "bid": mid * 0.98,
                            "ask": mid * 1.02,
                            "last": mid,
                            "volume": 100 + index + expiry_days,
                            "open_interest": 1000 + 10 * index + expiry_days,
                            "implied_volatility": iv,
                            "lineage_id": f"lin-quote-{contract_key}-{index}",
                            "stable_sequence": index * 100 + expiry_days,
                        }
                    )

            assets = 1_000_000 + 20_000 * math.sin(2 * math.pi * index / 10 + (0.0 if entity == "ASSET1" else 0.8)) + (50_000 if entity == "ASSET1" else 80_000)
            equity = assets * (0.55 if entity == "ASSET1" else 0.48)
            fundamentals.append(
                {
                    "date": date,
                    "fiscal_period_end": date,
                    "filed_at": available_at,
                    "available_at": available_at,
                    "decision_time": decision_time,
                    "underlying": entity,
                    "book_equity": equity,
                    "market_cap": spot * 10_000_000,
                    "net_income": 55_000 + 2_000 * math.sin(2 * math.pi * index / 10),
                    "gross_profit": 180_000 + 5_000 * math.cos(2 * math.pi * index / 10),
                    "operating_income": 100_000 + 3_000 * math.sin(2 * math.pi * index / 10 + 0.3),
                    "total_assets": assets,
                    "total_equity": equity,
                    "operating_cash_flow": 70_000 + 2_500 * math.cos(2 * math.pi * index / 10 + 0.2),
                    "debt": assets * 0.25,
                    "lineage_id": f"lin-fundamental-{entity}-{index}",
                    "stable_sequence": index * 2 + (0 if entity == "ASSET1" else 1),
                }
            )
            event_time = (timestamp + pd.Timedelta(days=3 + (index % 10), hours=12)).isoformat()
            events.append(
                {
                    "date": date,
                    "event_time": event_time,
                    "published_at": available_at,
                    "available_at": available_at,
                    "decision_time": decision_time,
                    "underlying": entity,
                    "event_id": f"earnings-{entity}-{index}",
                    "event_type": "EARNINGS",
                    "importance": 0.8,
                    "surprise": 0.01 * math.sin(index / 5),
                    "lineage_id": f"lin-event-{entity}-{index}",
                    "stable_sequence": index * 2 + (0 if entity == "ASSET1" else 1),
                }
            )
        curves.extend(
            [
                {
                    "date": date,
                    "available_at": available_at,
                    "decision_time": decision_time,
                    "curve_id": "BR_RATES",
                    "entity_id": "BR_RATES",
                    "tenor": tenor,
                    "rate": rate,
                    "basis": 0.25 + 0.02 * math.sin(2 * math.pi * index / 10),
                    "carry": 0.15 + 0.01 * math.cos(2 * math.pi * index / 10),
                    "roll_down": 0.05 + 0.005 * math.sin(2 * math.pi * index / 10),
                    "lineage_id": f"lin-curve-{tenor}-{index}",
                    "stable_sequence": index * 2 + offset,
                }
                for offset, (tenor, rate) in enumerate((("1Y", 10 + 0.15 * math.sin(2 * math.pi * index / 10)), ("5Y", 11 + 0.10 * math.cos(2 * math.pi * index / 10))))
            ]
        )

    created_at = created.isoformat()
    p2 = {
        "clean_underlying_panel": _artifact("clean_underlying_panel", underlying, created_at=created_at),
        "clean_macro_br_panel": _artifact("clean_macro_br_panel", macro_br, created_at=created_at),
        "clean_macro_us_panel": _artifact("clean_macro_us_panel", macro_us, created_at=created_at),
        "clean_benchmark_panel": _artifact("clean_benchmark_panel", benchmark, created_at=created_at),
        "clean_calendar_panel": _artifact("clean_calendar_panel", calendar, created_at=created_at),
        "clean_corporate_actions_panel": _artifact("clean_corporate_actions_panel", [], created_at=created_at),
        "quality_report_phase_2": _artifact("quality_report_phase_2", [], created_at=created_at, status="PASS"),
        "clean_option_contract_panel": _artifact("clean_option_contract_panel", option_contracts, created_at=created_at),
        "clean_option_quotes_panel": _artifact("clean_option_quotes_panel", option_quotes, created_at=created_at),
        "clean_event_reference_panel": _artifact("clean_event_reference_panel", events, created_at=created_at),
        "clean_fundamental_panel": _artifact("clean_fundamental_panel", fundamentals, created_at=created_at),
        "clean_curve_term_structure_panel": _artifact("clean_curve_term_structure_panel", curves, created_at=created_at),
    }
    references = [
        {
            "artifact_name": name,
            "artifact_id": artifact["artifact_id"],
            "schema_version": artifact.get("schema_version"),
            "content_hash": p2_legacy_digest(artifact),
            "lineage_id": artifact["lineage_id"],
        }
        for name, artifact in p2.items()
    ]
    p2["phase4_handoff_manifest"] = {
        "handoff_id": "handoff-p2",
        "created_at": created_at,
        "target_phase": "phase_04_feature_base",
        "artifact_ids": [artifact["artifact_id"] for artifact in p2.values()],
        "target_artifact_ids": [reference["artifact_id"] for reference in references],
        "artifact_refs": references,
        "lineage_id": "lin-p2-handoff",
        "pipeline_version": PIPELINE_VERSION,
        "quality_status": "PASS",
        "no_hidden_bundle": True,
    }

    def semantic(name: str, records: list[dict[str, Any]], producer: str) -> dict[str, Any]:
        return _artifact(
            name,
            records,
            created_at=created_at,
            run_id=context.run_id,
            cycle_id=context.cycle_id,
            as_of_time=context.as_of_time.isoformat(),
            schema_id=f"p3.{name}.semantic",
            schema_version="1.0.0",
            quality_status="PASS",
            quality_reasons=[],
            producer_module_id=producer,
        )

    social: list[dict[str, Any]] = []
    disagreement: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    memory: list[dict[str, Any]] = []
    for index, timestamp in enumerate(dates):
        date = timestamp.date().isoformat()
        available_at = (timestamp + pd.Timedelta(hours=19)).isoformat()
        decision_time = (timestamp + pd.Timedelta(hours=21)).isoformat()
        signal = 0.3 * math.sin(2 * math.pi * index / 10)
        for entity_offset, entity in enumerate(("ASSET1", "ASSET2")):
            base = {
                "date": date,
                "as_of_date": date,
                "available_at": available_at,
                "decision_time": decision_time,
                "underlying": entity,
                "lineage_id": f"lin-social-{entity}-{index}",
                "stable_sequence": index * 2 + entity_offset,
            }
            social.append(
                {
                    **base,
                    "social_feature_id": "sentiment",
                    "feature_name": "sentiment",
                    "feature_value": signal + (0.05 if entity == "ASSET1" else -0.02),
                    "feature_type": "CONTINUOUS",
                    "source_quality_score": 0.85,
                    "evidence_count": 2,
                    "agent_agreement_score": 0.7,
                    "agent_disagreement_score": 0.3,
                    "reference_date": date,
                    "pipeline_version": PIPELINE_VERSION,
                }
            )
            disagreement.append(
                {
                    **base,
                    "proposition_id": "p1",
                    "horizon": "21d",
                    "effective_sample_size": 10.0,
                    "disagreement_score": 0.25 + 0.05 * math.cos(2 * math.pi * index / 10),
                }
            )
            evidence.append(
                {
                    **base,
                    "proposition_id": "p1",
                    "horizon": "21d",
                    "claim_id": f"claim-{index}",
                    "evidence_id": f"evidence-{entity}-{index}",
                    "relation": "SUPPORTS",
                    "source_quality_score": 0.8,
                }
            )
            memory.append(
                {
                    **base,
                    "proposition_id": "p1",
                    "horizon": "21d",
                    "context_memory_feature_id": "memory-1",
                    "feature_name": "memory_state",
                    "feature_value": 0.2 * math.cos(2 * math.pi * index / 10),
                }
            )
    hypotheses = [
        {
            "hypothesis_id": "h1",
            "artifact_id": "h1",
            "created_at": created_at,
            "available_at": context.as_of_time.isoformat(),
            "decision_time": context.as_of_time.isoformat(),
            "as_of_time": context.as_of_time.isoformat(),
            "underlying_id": "ASSET1",
            "hypothesis_text": "Falsifiable hypothesis",
            "evidence_count": 1,
            "source_quality_score": 0.8,
            "lineage_id": "lin-h1",
            "pipeline_version": PIPELINE_VERSION,
            "stable_sequence": 1,
        }
    ]
    p3 = {
        "social_feature_panel": semantic("social_feature_panel", social, "P3.S30.M01"),
        "evidence_tag_panel": semantic("evidence_tag_panel", evidence, "P3.S29.M02"),
        "agent_disagreement_panel": semantic("agent_disagreement_panel", disagreement, "P3.S29.M01"),
        "context_memory_feature_panel": semantic("context_memory_feature_panel", memory, "P3.S30.M02"),
        "hypothesis_registry": semantic("hypothesis_registry", hypotheses, "P3.S30.M03"),
    }
    grains = {
        "social_feature_panel": ["date", "underlying", "social_feature_id"],
        "evidence_tag_panel": ["underlying", "proposition_id", "horizon", "claim_id", "evidence_id"],
        "agent_disagreement_panel": ["underlying", "proposition_id", "horizon", "as_of_date"],
        "context_memory_feature_panel": ["underlying", "proposition_id", "horizon", "context_memory_feature_id"],
        "hypothesis_registry": ["hypothesis_id", "created_at"],
    }
    entries = [
        {
            "artifact_name": name,
            "artifact_id": artifact["artifact_id"],
            "schema_id": artifact["schema_id"],
            "schema_version": artifact["schema_version"],
            "content_hash": content_hash(artifact),
            "row_count": len(artifact["records"]),
            "grain": grains[name],
            "producer_module_id": artifact["producer_module_id"],
            "lineage_id": artifact["lineage_id"],
            "available_at": created_at,
            "quality_status": "PASS",
        }
        for name, artifact in p3.items()
    ]
    p3["phase4_social_handoff_manifest"] = {
        "artifact_id": "p3-handoff",
        "created_at": created_at,
        "lineage_id": "lin-p3-handoff",
        "pipeline_version": PIPELINE_VERSION,
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": context.as_of_time.isoformat(),
        "schema_id": "p3.s30.phase4_social_handoff_manifest.semantic",
        "schema_version": "1.0.0",
        "quality_status": "PASS",
        "quality_reasons": [],
        "expected_output_count": 6,
        "entries": entries,
        "complete": True,
    }
    return {**p2, **p3}, context
