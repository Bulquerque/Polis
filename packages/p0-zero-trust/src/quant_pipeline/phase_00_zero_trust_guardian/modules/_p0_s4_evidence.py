from __future__ import annotations

from typing import Any
import re

from ._module_executor import ContractValidationError
from ._p0_s4_test_evidence import digest


LINEAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_REQUIRED = (
    "global_test_report",
    "hash_integrity_report",
    "lineage_integrity_report",
    "code_quality_report",
)
OPTIONAL_CATEGORIES = {
    "forbidden_connection_report": "ARCHITECTURE",
    "io_compatibility_report": "CONTRACT",
    "schema_compatibility_report": "SCHEMA",
    "forbidden_field_report": "CONTRACT",
    "artifact_format_validation_report": "INTEGRITY",
    "artifact_integrity_report": "INTEGRITY",
    "immutability_report": "INTEGRITY",
}
DEFAULT_CATEGORIES = {
    "global_test_report": "TEST",
    "hash_integrity_report": "INTEGRITY",
    "lineage_integrity_report": "INTEGRITY",
    "code_quality_report": "CODE_QUALITY",
}


def requirement_policy(config: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    raw = config.get("zero_trust_evidence_requirements")
    required = list(DEFAULT_REQUIRED)
    categories = {**DEFAULT_CATEGORIES, **OPTIONAL_CATEGORIES}
    if raw is None:
        return required, categories
    if not isinstance(raw, dict):
        raise ContractValidationError("zero_trust_evidence_requirements must be a mapping")
    if "required" in raw:
        if not isinstance(raw["required"], list) or not all(isinstance(x, str) and x for x in raw["required"]):
            raise ContractValidationError("evidence required policy must be a string list")
        required = list(dict.fromkeys(raw["required"]))
    if isinstance(raw.get("categories"), dict):
        categories.update({str(k): str(v) for k, v in raw["categories"].items()})
    return required, categories


def evidence_record(name: str, item: dict[str, Any], category: str, required: bool) -> dict[str, Any]:
    artifact_id = item.get("artifact_id")
    lineage = item.get("lineage_id")
    status = item.get("status")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ContractValidationError(f"{name} lacks artifact_id")
    if not isinstance(lineage, str) or LINEAGE.fullmatch(lineage) is None:
        raise ContractValidationError(f"{name} lacks traceable SHA-256 lineage")
    if status not in {"PASS", "FAIL", "BLOCKED", "PARTIAL", "NOT_RUN", "WARNING"}:
        raise ContractValidationError(f"{name} lacks a recognized status")
    accepted = status == "PASS" and item.get("release_blocking") is not True
    return {
        "evidence_type": name,
        "evidence_category": category,
        "artifact_id": artifact_id,
        "lineage_id": lineage,
        "content_digest": f"sha256:{digest(item)}",
        "status": status,
        "required": required,
        "accepted": accepted,
    }


def summarize_categories(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories = {}
    for record in records:
        bucket = categories.setdefault(record["evidence_category"], {"evidence_category": record["evidence_category"], "evidence_count": 0, "accepted_count": 0})
        bucket["evidence_count"] += 1
        bucket["accepted_count"] += int(record["accepted"])
    result = []
    for name in sorted(categories):
        item = categories[name]
        item["status"] = "PASS" if item["evidence_count"] == item["accepted_count"] else "FAIL"
        result.append(item)
    return result
