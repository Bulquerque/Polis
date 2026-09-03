from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "capabilities" / "products" / "s31"
CONFIG = (
    ROOT
    / "src"
    / "quant_pipeline"
    / "phase_03_agents_rag_memory"
    / "runtime_engine"
    / "assets"
    / "config"
    / "products"
    / "S31_P9_CONSUMER_COMPATIBILITY.yaml"
)


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def execution_context() -> dict:
    return deepcopy(load_json("execution_context.json"))


def m01_inputs() -> dict:
    return deepcopy(load_json("m01_valid_inputs.json"))


def compatibility_config() -> dict:
    return deepcopy(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))


def run_m01(inputs: dict | None = None, context: dict | None = None) -> dict:
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S31_M01_p9_evaluation_evidence_bundle_builder import run_module

    return run_module(
        inputs if inputs is not None else m01_inputs(),
        {"execution_context": context if context is not None else execution_context()},
    )["outputs"]["p9_evaluation_evidence_bundle"]


def run_m02(
    bundle: dict | None = None,
    inputs: dict | None = None,
    context: dict | None = None,
    compatibility: dict | None = None,
) -> dict:
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S31_M02_p9_context_learning_handoff_builder import run_module

    source = inputs if inputs is not None else m01_inputs()
    payload = {
        "p9_evaluation_evidence_bundle": bundle if bundle is not None else run_m01(source, context),
        "phase4_social_handoff_manifest": source["phase4_social_handoff_manifest"],
        "variable_evolution_input_manifest": source["variable_evolution_input_manifest"],
        "phase3_run_snapshot": source["phase3_run_snapshot"],
    }
    return run_module(
        payload,
        {
            "execution_context": context if context is not None else execution_context(),
            "p9_consumer_compatibility": (
                compatibility if compatibility is not None else compatibility_config()
            ),
        },
    )["outputs"]["p9_context_learning_handoff_manifest"]
