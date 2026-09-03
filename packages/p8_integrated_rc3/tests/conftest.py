"""Global test bootstrap for source-tree and subprocess CLI tests.

The integrated release is a ``src``-layout package.  Pytest's ``pythonpath``
option updates the current interpreter, but subprocess CLI tests inherit only
the environment.  Keep both execution modes pointed at the same canonical
source tree without installing an editable package.
"""

from __future__ import annotations

import os
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"

_existing = os.environ.get("PYTHONPATH")
_source_text = str(_SOURCE_ROOT)
if _existing:
    entries = _existing.split(os.pathsep)
    if _source_text not in entries:
        os.environ["PYTHONPATH"] = os.pathsep.join((_source_text, _existing))
else:
    os.environ["PYTHONPATH"] = _source_text
