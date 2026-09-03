from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import yaml


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_inputs(plan_root: Path) -> dict[str, object]:
    return {
        "pit_validated_context": {
            "schema_version": "pit_validated_context.s17.v1",
            "lineage_id": "lineage:pit-test",
            "records": [
                {
                    "record_id": "ctx:apple-test",
                    "record_type": "EVENT",
                    "source_event_id": "event:apple-test",
                    "subject": "Apple Inc. filing",
                    "content_hash": _hash("apple-test"),
                    "event_time": "2026-07-27T13:00:00Z",
                    "available_at": "2026-07-27T13:01:00Z",
                    "evidence_refs": ["evidence:apple-test"],
                    "lineage_id": "lineage:apple-test",
                    "stimulus_type": "FILING_EVENT",
                    "entity_ids": ["entity:apple-inc"],
                    "identifier_hints": [
                        {
                            "id_type": "TICKER",
                            "id_value": "AAPL",
                            "mic": "XNAS",
                            "exchange_code": "US",
                            "currency": "USD",
                        }
                    ],
                    "proposition_id": "directional_outlook",
                    "horizon": "21d",
                    "salience_features": {
                        "source_quality": 0.9,
                        "novelty": 0.7,
                        "subject_relevance": 0.9,
                        "event_severity": 0.6,
                        "information_specificity": 0.9,
                    },
                }
            ],
        },
        "graph_rag_artifact": {
            "schema_version": "graph_rag_artifact.s17.v1",
            "artifact_id": "artifact:graph-test",
            "created_at": "2026-07-27T13:05:00Z",
            "as_of": "2026-07-27T13:05:00Z",
            "lineage_id": "lineage:graph-test",
            "nodes": [],
        },
        "phase3_run_snapshot": {
            "schema_version": "phase3_run_snapshot.s17.v1",
            "run_id": "run:test",
            "cycle_id": "cycle:test",
            "target_cycle_id": "cycle:test",
            "snapshot_id": "snapshot:test",
            "as_of": "2026-07-27T14:00:00Z",
            "seed": 17,
            "lineage_id": "lineage:snapshot-test",
        },
        "stimulus_bus_config": yaml.safe_load(
            (plan_root / "src/quant_pipeline/phase_03_agents_rag_memory/runtime_engine/assets/config/context/s17/STIMULUS_EVENT_BUS_CONFIG.yaml").read_text(encoding="utf-8")
        ),
        "entity_underlying_map_config": yaml.safe_load(
            (plan_root / "src/quant_pipeline/phase_03_agents_rag_memory/runtime_engine/assets/config/context/s17/ENTITY_UNDERLYING_MAP_CONFIG.yaml").read_text(encoding="utf-8")
        ),
        "proposition_registry_config": yaml.safe_load(
            (plan_root / "src/quant_pipeline/phase_03_agents_rag_memory/runtime_engine/assets/config/context/s17/PROPOSITION_REGISTRY.yaml").read_text(encoding="utf-8")
        ),
    }


def deep_copy_inputs(plan_root: Path) -> dict[str, object]:
    return copy.deepcopy(build_inputs(plan_root))
