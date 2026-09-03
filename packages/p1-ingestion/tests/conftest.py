"""Make this phase test suite independently collectable from the workspace root."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# P3 supplies the regular shared ``quant_pipeline`` package in the co-installed
# workspace.  Add this phase's portion explicitly so imports remain isolated.
import quant_pipeline

PHASE_NAMESPACE = str(ROOT / "src" / "quant_pipeline")
if PHASE_NAMESPACE not in quant_pipeline.__path__:
    quant_pipeline.__path__.append(PHASE_NAMESPACE)
