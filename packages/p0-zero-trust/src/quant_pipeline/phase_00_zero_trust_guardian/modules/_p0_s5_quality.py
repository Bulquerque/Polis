from __future__ import annotations

# Backward-compatible S5 facade. New code should import the focused S5 components.
from ._s5_ast_metrics import parse_python
from ._s5_schema import validate_artifact
from ._s5_core import (
    digest_payload,
    envelope,
    load_mapping,
    module_result,
    require_config,
    require_inputs,
    source_files,
)

__all__ = (
    "digest_payload", "envelope", "load_mapping", "module_result", "parse_python",
    "require_config", "require_inputs", "source_files", "validate_artifact",
)
