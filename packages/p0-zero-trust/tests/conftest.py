from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC = str(PACKAGE_ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# The workspace co-installs every phase below the shared ``quant_pipeline``
# namespace.  P3 is a regular package, so Python will not discover this
# phase's source tree unless its namespace path is extended explicitly.
import quant_pipeline

PHASE_NAMESPACE = str(PACKAGE_ROOT / "src" / "quant_pipeline")
if PHASE_NAMESPACE not in quant_pipeline.__path__:
    quant_pipeline.__path__.append(PHASE_NAMESPACE)
