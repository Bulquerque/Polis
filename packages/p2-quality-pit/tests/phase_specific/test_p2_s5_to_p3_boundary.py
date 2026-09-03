from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
P2_ROOT = ROOT / "phase_02_extracted" / "phase_02_quality_pit_agent_package_RC4_1"
P3_ROOT = ROOT / "phase_03_extracted" / "phase_03_agents_rag_memory_agent_package_RC4_1"
sys.path.insert(0, str(P2_ROOT / "src"))
sys.path.insert(0, str(P3_ROOT / "src"))

S5 = importlib.import_module(
    "quant_pipeline.phase_02_quality_pit.modules.P2_S5_M01_context_document_event_cleaner"
)
P3_INTAKE = importlib.import_module(
    "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M01_phase2_handoff_contract_validator"
)

CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2024-06-01T00:00:00Z",
}


def test_s5_outputs_are_directly_accepted_by_p3_context_intake():
    quality = {
        "artifact_id": "source-quality-1",
        "created_at": CONFIG["created_at"],
        "lineage_id": "lineage-quality",
        "pipeline_version": CONFIG["pipeline_version"],
        "records": [
            {
                "source_id": "news-1",
                "source_name": "News Source",
                "source_type": "api",
                "quality_score": 0.9,
                "readability_status": "readable",
                "error_flag": False,
                "warning_flag": False,
                "declared_available_at": "2024-05-31T12:00:00Z",
                "lineage_id": "lineage-quality-news-1",
            }
        ],
    }
    s5_outputs = S5.run_module(
        {
            "identifier_harmonized_bundle": {
                "records": [
                    {
                        "source_id": "news-1",
                        "source_name": "News Source",
                        "record_domain": "DOCUMENT",
                        "document_type": "news",
                        "document_title": "Earnings released",
                        "document_text_or_path": "Company released earnings.",
                        "reference_date": "2024-05-31",
                        "available_at": "2024-05-31T12:00:00Z",
                        "ingested_at": "2024-05-31T12:00:05Z",
                        "language": "en",
                        "lineage_id": "lineage-document",
                    }
                ]
            },
            "source_quality_panel": quality,
        },
        CONFIG,
    )["outputs"]

    p3_inputs = {
        **s5_outputs,
        "source_quality_panel": quality,
            "context_handoff_manifest": {
                "artifact_id": "context-handoff-1",
                "created_at": CONFIG["created_at"],
                "target_phase": "phase_03_agents_rag_memory",
                "lineage_id": "lineage-context-handoff",
                "pipeline_version": CONFIG["pipeline_version"],
                "artifact_ids": [
                    s5_outputs["clean_context_source_panel"]["artifact_id"],
                    s5_outputs["clean_document_panel"]["artifact_id"],
                    s5_outputs["clean_event_reference_panel"]["artifact_id"],
                    quality["artifact_id"],
                ],
                "records": [],
        },
        "phase3_handoff_manifest": {
            "handoff_id": "phase3-handoff-1",
            "created_at": CONFIG["created_at"],
            "target_phase": "phase_03_agents_rag_memory",
                "artifact_ids": [
                    s5_outputs["clean_context_source_panel"]["artifact_id"],
                    s5_outputs["clean_document_panel"]["artifact_id"],
                    s5_outputs["clean_event_reference_panel"]["artifact_id"],
                    quality["artifact_id"],
                ],
            "lineage_id": "lineage-phase3-handoff",
            "pipeline_version": CONFIG["pipeline_version"],
            "records": [],
        },
    }

    result = P3_INTAKE.run_module(p3_inputs, CONFIG)
    outputs = result["outputs"]
    assert outputs["validated_phase2_handoff"]["validation_status"] in {"READY", "DEGRADED"}
