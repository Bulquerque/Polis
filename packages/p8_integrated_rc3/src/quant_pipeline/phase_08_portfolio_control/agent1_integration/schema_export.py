"""JSON Schema export for the integration receipt."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import Agent1IntegrationReceiptV1


def export_schema(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    path = target / "P8_AGENT1_INTEGRATION_RECEIPT_V1.schema.json"
    schema = Agent1IntegrationReceiptV1.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
