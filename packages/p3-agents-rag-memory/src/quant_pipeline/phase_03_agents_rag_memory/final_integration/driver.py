"""External driver interface for producing genuine integration evidence."""
from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Protocol


class IntegrationEvidenceDriver(Protocol):
    def run(self, config: dict[str, Any], output_dir: Path) -> dict[str, Any]: ...


def load_driver(reference: str) -> IntegrationEvidenceDriver:
    if ":" not in reference:
        raise ValueError("driver must use module:factory")
    module_name, factory_name = reference.split(":", 1)
    factory = getattr(importlib.import_module(module_name), factory_name)
    driver = factory()
    if not hasattr(driver, "run"):
        raise TypeError("driver must expose run(config, output_dir)")
    return driver


def run_driver(
    reference: str,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    driver = load_driver(reference)
    result = driver.run(config, output_dir)
    if inspect.isawaitable(result):
        raise TypeError(
            "integration driver must be synchronous to preserve one explicit transaction boundary"
        )
    if not isinstance(result, dict):
        raise TypeError("driver result must be a mapping")
    return result
