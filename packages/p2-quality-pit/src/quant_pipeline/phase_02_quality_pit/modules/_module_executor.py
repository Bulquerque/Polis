"""Compatibility primitives for explicit P2 module implementations.

P2 previously used a generic semantic-output generator in this module.  That
made missing business data look valid by fabricating defaults.  The public
helper names are retained for compatibility, but execution now delegates to the
real explicit module wrapper instead of synthesizing records.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any
import hashlib
import json

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[4]
MODULE_CONTRACT_ROOT = PACKAGE_ROOT / "modules"


class ContractValidationError(ValueError):
    """Raised when a P2 contract or semantic invariant is violated."""


def fail_fast(condition: bool, message: str) -> None:
    if not condition:
        raise ContractValidationError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    fail_fast(path.exists(), f"missing YAML file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fail_fast(isinstance(data, dict), f"YAML must be a mapping: {path}")
    return data


def _stable_digest(payload: Any) -> str:
    blob = json.dumps(
        payload,
        sort_keys=True,
        default=str,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_module_contract(contract_filename: str) -> dict[str, Any]:
    return load_yaml(MODULE_CONTRACT_ROOT / contract_filename)


def execute_module(
    contract_filename: str,
    inputs: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """Execute the explicit wrapper bound to ``contract_filename``.

    The function remains available as a compatibility entry point, but it no
    longer fabricates required fields.  Every module must implement its own
    semantics in ``run_module`` and therefore fails closed on missing data.
    """
    fail_fast(isinstance(inputs, dict), "inputs must be a dict")
    config = config or {}
    fail_fast(isinstance(config, dict), "config must be a dict")

    spec = load_module_contract(contract_filename)
    expected_module_id = spec.get("module_id")
    module_stem = Path(contract_filename).stem
    wrapper = import_module(
        f"quant_pipeline.phase_02_quality_pit.modules.{module_stem}"
    )
    fail_fast(
        hasattr(wrapper, "run_module"),
        f"explicit module wrapper has no run_module: {module_stem}",
    )
    result = wrapper.run_module(inputs, config)
    fail_fast(isinstance(result, dict), f"module result must be a dict: {module_stem}")
    fail_fast(
        result.get("module_id") == expected_module_id,
        f"module_id mismatch for {module_stem}: expected {expected_module_id}, got {result.get('module_id')}",
    )
    return result
