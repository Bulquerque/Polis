from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures" / "capabilities" / "society" / "s26"
def valid(name: str): return json.loads((FIX / "valid" / f"{name}.json").read_text(encoding="utf-8"))
def invalid(name: str): return json.loads((FIX / "invalid" / f"{name}.json").read_text(encoding="utf-8"))
