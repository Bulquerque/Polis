"""Small assembly helpers for P3.S38."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from .models import ExtensionLineage, HandlerBundleManifest


def require_inputs(inputs: Mapping[str, Any], module_id: str, required: tuple[str, ...]) -> None:
    """Fail closed when a S38 module receives an incomplete contract payload."""
    if not isinstance(inputs, Mapping):
        raise ValueError(f"P3_S38_INPUT_INVALID:{module_id}:inputs must be a mapping")
    missing = tuple(name for name in required if name not in inputs or inputs[name] is None)
    if missing:
        raise ValueError(f"P3_S38_INPUT_INVALID:{module_id}:missing={','.join(missing)}")


def lineage_for(module_id: str, inputs: Mapping[str, Any], transformation_id: str) -> ExtensionLineage:
    source_ids = tuple(sorted(str(key) for key in inputs))
    source_hashes = {source_id: content_hash(inputs[source_id]) for source_id in source_ids}
    return ExtensionLineage(
        lineage_id=f"{module_id}:{content_hash(source_hashes)[:20]}", producer_module_id=module_id,
        source_artifact_ids=source_ids, source_hashes=source_hashes, transformation_ids=(transformation_id,),
    )


def build_bundle_output(
    *, inputs: Mapping[str, Any], module_id: str, bundle_builder: Callable[[ExtensionLineage], HandlerBundleManifest],
    bundle_output_name: str, report_output_name: str, report_payload: Mapping[str, Any],
):
    if not isinstance(inputs, Mapping):
        raise ValueError(f"P3_S38_INPUT_INVALID:{module_id}:inputs must be a mapping")
    lineage = lineage_for(module_id, inputs, f"{module_id}.bundle.v1")
    bundle = bundle_builder(lineage)
    report = dict(report_payload)
    report.update({"schema_version": "p3.s38.v1", "producer_module_id": module_id, "lineage_id": lineage.lineage_id})
    report["content_hash"] = content_hash(report)
    return {bundle_output_name: bundle.model_dump(mode="json"), report_output_name: report}
