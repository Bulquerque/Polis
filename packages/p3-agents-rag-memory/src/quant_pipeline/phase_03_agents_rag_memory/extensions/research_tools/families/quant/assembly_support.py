"""Small assembly helpers shared by the four P3.S39 modules."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .models import ExtensionLineage, HandlerBundleManifest


def lineage_for(module_id: str, inputs: Mapping[str, Any], transformation_id: str) -> ExtensionLineage:
    source_ids = tuple(sorted(str(key) for key in inputs))
    source_hashes = {source_id: content_hash(inputs[source_id]) for source_id in source_ids}
    return ExtensionLineage(
        lineage_id=f"{module_id}:{content_hash(source_hashes)[:20]}",
        producer_module_id=module_id,
        source_artifact_ids=source_ids,
        source_hashes=source_hashes,
        transformation_ids=(transformation_id,),
    )


def build_bundle_output(
    *,
    inputs: Mapping[str, Any],
    module_id: str,
    bundle_builder: Callable[[ExtensionLineage], HandlerBundleManifest],
    bundle_output_name: str,
    manifest_output_name: str,
    manifest_payload: Mapping[str, Any],
) -> dict[str, Any]:
    lineage = lineage_for(module_id, inputs, f"{module_id}.bundle.v1")
    bundle = bundle_builder(lineage)
    manifest = dict(manifest_payload)
    manifest.update(
        {
            "schema_version": "p3.s39.v1",
            "producer_module_id": module_id,
            "lineage_id": lineage.lineage_id,
        }
    )
    manifest["content_hash"] = content_hash(manifest)
    return {
        bundle_output_name: bundle.model_dump(mode="json"),
        manifest_output_name: manifest,
    }
