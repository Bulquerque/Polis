from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WORKSPACE_ROOT = ROOT.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# The workspace co-installs P3 and P4 under the shared ``quant_pipeline``
# namespace.  P3 is a regular package, so its ``__path__`` does not discover
# P4's source tree by itself.  Extend that namespace only for the P4 test
# process; production packages remain free of a second root ``__init__.py``.
import quant_pipeline

P4_NAMESPACE = str(SRC / "quant_pipeline")
if P4_NAMESPACE not in quant_pipeline.__path__:
    quant_pipeline.__path__.append(P4_NAMESPACE)
