from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures" / "capabilities" / "society" / "s28" / "valid"

def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))

def m01_inputs() -> dict: return deepcopy(load("m01_inputs.json"))
def m02_inputs() -> dict: return deepcopy(load("m02_inputs.json"))
def m03_inputs() -> dict: return deepcopy(load("m03_inputs.json"))
