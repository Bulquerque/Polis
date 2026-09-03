"""Create fail-closed templates for the integration evidence bundle."""
from __future__ import annotations

import json
from pathlib import Path

FILES = (
    "integration_entry_evidence.json",
    "evaluation_dataset_manifest.json",
    "evaluation_split_manifest.json",
    "experiment_registry.json",
    "commitment_coverage_report.json",
    "population_calibration_bundle.json",
    "social_graph_calibration_report.json",
    "activation_trust_sensitivity_report.json",
    "variant_execution_manifest.json",
    "evaluation_observation_panel.json",
    "runtime_cost_latency_panel.json",
    "cross_phase_receipts.json",
    "qualification_summary.json",
    "promotion_candidate_bundle.json",
    "p0_promotion_decision.json",
)


def write_templates(output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name in FILES:
        path = output_dir / name
        payload: dict[str, object] = {
            "template": True,
            "status": "FAIL_NOT_QUALIFIED",
            "instructions": (
                "Replace this template with real, release-bound, signed and hash-linked evidence. "
                "Templates never satisfy an integration gate."
            ),
        }
        if name == "cross_phase_receipts.json":
            payload["receipts"] = []
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return tuple(paths)
