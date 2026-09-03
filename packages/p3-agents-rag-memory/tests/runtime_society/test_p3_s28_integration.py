from __future__ import annotations
from pathlib import Path
import sys

_TESTS_ROOT = Path(__file__).resolve().parents[1]
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from quant_pipeline.phase_03_agents_rag_memory.s28.entrypoints import run_m01,run_m02,run_m03
from s28_test_support import m01_inputs,m02_inputs,m03_inputs

def test_complete_s28_flow() -> None:
    tag=run_m01(m01_inputs())["tag_projection_panel"]
    v=m02_inputs(); v["tag_projection_panel"]=tag
    society=run_m02(v)["synthetic_society_state_panel"]
    q=m03_inputs(); q["synthetic_society_state_panel"]=society
    validated=run_m03(q)["validated_society_state_panel"]
    assert validated["records"][0]["quality"]["status"] in {"PASS","DEGRADED"}
    assert validated["records"][0]["features"] == society["records"][0]["features"]

def test_forbidden_authority_rejected() -> None:
    value=m01_inputs(); value["future_return"] = 1.0
    try: run_m01(value)
    except Exception: pass
    else: raise AssertionError("forbidden field accepted")
