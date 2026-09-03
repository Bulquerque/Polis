"""Environment-supplied production P3 pipeline driver with mandatory qualification."""
from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ..final_integration.models import PublicKeyRecord
from .runtime_qualification_gate import validate_runtime_bundle


class ProductionPipelineDriver(Protocol):
    async def run(self, config: Mapping[str, Any]) -> Mapping[str, Any]: ...


def load_driver(reference: str) -> ProductionPipelineDriver:
    if ":" not in reference:
        raise ValueError("driver reference must use module:factory")
    module_name, factory_name = reference.split(":", 1)
    factory = getattr(importlib.import_module(module_name), factory_name)
    driver = factory()
    if not hasattr(driver, "run"):
        raise TypeError("driver must expose async run(config)")
    return driver


async def run_real_pipeline(
    *,
    driver_ref: str,
    config_path: Path,
    keyring: Mapping[str, PublicKeyRecord],
    release_id: str,
    release_sha256: str,
    output_dir: Path,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    driver = load_driver(driver_ref)
    bundle = dict(await driver.run(config))
    result = validate_runtime_bundle(
        bundle,
        keyring=keyring,
        release_id=release_id,
        release_sha256=release_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "production_pipeline_bundle.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "runtime_qualification.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result.model_dump(mode="json")
