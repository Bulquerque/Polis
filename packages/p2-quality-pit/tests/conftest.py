"""Make this phase test suite independently collectable from the workspace root."""

from pathlib import Path
import sys
import importlib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Each phase ships its own ``quant_pipeline`` distribution.  Some of those
# distributions contain a regular package initializer while others are
# namespace portions.  Extend the loaded package explicitly so the P2 tests
# can exercise P3/P4/P6 boundaries from a clean checkout, independent of
# PYTHONPATH ordering.
PROJECT_ROOT = ROOT.parents[1]
quant_pipeline = importlib.import_module("quant_pipeline")
for phase_root in sorted(PROJECT_ROOT.glob("phase_*_extracted/*_agent_package_RC4_1")):
    package_path = phase_root / "src" / "quant_pipeline"
    if package_path.is_dir() and str(package_path) not in quant_pipeline.__path__:
        quant_pipeline.__path__.append(str(package_path))
