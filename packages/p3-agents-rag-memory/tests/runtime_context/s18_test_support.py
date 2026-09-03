from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import yaml

from quant_pipeline.phase_03_agents_rag_memory.s17.service import run_subphase as run_s17
from quant_pipeline.phase_03_agents_rag_memory.s18.hashing import sha256_hex
from quant_pipeline.phase_03_agents_rag_memory.s18.models import PriorCycleEndogenousStimulusQueue

from .s17_test_support import deep_copy_inputs as s17_inputs


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_inputs(plan_root: Path) -> dict[str, object]:
    upstream = s17_inputs(plan_root)
    resolved = run_s17(upstream).resolved_external_stimulus_stream.model_dump(mode="json")
    snapshot = copy.deepcopy(upstream["phase3_run_snapshot"])
    queue = {
        "schema_version": "next_cycle_endogenous_stimulus_queue.v2",
        "contract_version": "p3.s26.v1",
        "queue_id": "queue:s18-test",
        "source_run_id": snapshot["run_id"],
        "source_cycle_id": "cycle:test-prior",
        "target_cycle_id": snapshot["cycle_id"],
        "created_at": "2026-07-27T12:00:00Z",
        "items": [
            {
                "stimulus_id": "stim:s18-followup",
                "origin_type": "ATTENTION_FOLLOWUP",
                "source_event_id": "intent:s18-followup",
                "causal_parent_id": "belief:s18-parent",
                "created_cycle_id": "cycle:test-prior",
                "target_cycle_id": snapshot["cycle_id"],
                "event_time": "2026-07-27T12:10:00Z",
                "available_at": "2026-07-27T12:11:00Z",
                "expires_at": "2026-07-29T00:00:00Z",
                "subject": "Revisit Apple after prior uncertainty",
                "stimulus_type": "ATTENTION_FOLLOWUP_EVENT",
                "intensity": 0.7,
                "salience": 0.65,
                "priority": 70,
                "resolution_status": "RESOLVED_ONE",
                "underlying_candidates": [
                    {
                        "underlying_id": "figi:BBG000B9XRY4",
                        "weight": 1.0,
                        "mic": "XNAS",
                        "security_type": "Common Stock",
                        "identifiers": [],
                    }
                ],
                "selected_underlying_id": "figi:BBG000B9XRY4",
                "proposition_id": "directional_outlook",
                "horizon": "21d",
                "proposition_status": "RESOLVED",
                "content_hash": _hash("s18-followup"),
                "evidence_refs": ["evidence:s18-followup"],
                "lineage_id": "lineage:s18-followup",
                "warnings": [],
            }
        ],
        "lineage_id": "lineage:s18-queue",
        "content_hash": "0" * 64,
        "status": "READY",
        "warnings": [],
        "metrics": {"generated_count": 1, "warning_count": 0},
    }
    queue = PriorCycleEndogenousStimulusQueue.model_validate(queue).model_dump(mode="json")
    queue.pop("content_hash")
    queue["content_hash"] = sha256_hex(queue)
    return {
        "resolved_external_stimulus_stream": resolved,
        "prior_cycle_endogenous_stimulus_queue": queue,
        "phase3_run_snapshot": snapshot,
        "stimulus_event_bus_config": yaml.safe_load(
            (plan_root / "src/quant_pipeline/phase_03_agents_rag_memory/runtime_engine/assets/config/context/s18/STIMULUS_EVENT_BUS_S18_CONFIG.yaml").read_text(
                encoding="utf-8"
            )
        ),
    }


def deep_copy_inputs(plan_root: Path) -> dict[str, object]:
    return copy.deepcopy(build_inputs(plan_root))
