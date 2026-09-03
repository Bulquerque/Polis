"""Load the unified P3 source tree without executing heavyweight initializers."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(os.environ.get("MERGED_P3_ROOT", Path(__file__).resolve().parents[4])).resolve()
SRC = ROOT / "src"
PACKAGES = {
    "quant_pipeline": SRC / "quant_pipeline",
    "quant_pipeline.phase_03_agents_rag_memory": SRC / "quant_pipeline" / "phase_03_agents_rag_memory",
}
for name, path in PACKAGES.items():
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        module.__package__ = name
        sys.modules[name] = module
