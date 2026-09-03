from __future__ import annotations

from ._module_executor import PIPELINE_VERSION
from ._p0_s4_evidence import OPTIONAL_CATEGORIES, evidence_record, requirement_policy, summarize_categories
from ._p0_s4_test_evidence import artifact, created_at, digest, envelope, require_call, validate_output


INPUTS = ["global_test_report", "hash_integrity_report", "lineage_integrity_report", "code_quality_report"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_call(inputs, config, INPUTS)
    required, categories = requirement_policy(config)
    evidence_names = list(dict.fromkeys([*INPUTS, *(name for name in OPTIONAL_CATEGORIES if name in inputs)]))
    missing = sorted(set(required).difference(evidence_names))
    records = []
    for name in evidence_names:
        item = artifact(inputs[name], name)
        records.append(evidence_record(name, item, categories.get(name, "OTHER"), name in required))
    duplicate_types = sorted(name for name in {r["evidence_type"] for r in records} if sum(x["evidence_type"] == name for x in records) > 1)
    traceable = all(record["lineage_id"].startswith("sha256:") for record in records)
    required_records = [record for record in records if record["required"]]
    complete = not missing and not duplicate_types and len(required_records) == len(required)
    all_required_passing = complete and all(record["accepted"] for record in required_records)
    blocking = not complete or not traceable or not all_required_passing
    category_summary = summarize_categories(records)
    fingerprint = digest({"records": records, "required": required, "missing": missing})
    package = {
        "artifact_id": f"zero-trust-evidence-package-{fingerprint[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
        "evidence_policy_version": "zero_trust_evidence_requirements.v2",
        "required_evidence_count": len(required),
        "evidence_count": len(records),
        "evidence": records,
        "categories": category_summary,
        "missing_evidence": missing,
        "duplicate_evidence": duplicate_types,
        "evidence_complete": complete,
        "release_evidence_traceable": traceable,
        "all_evidence_passing": all_required_passing,
        "status": "FAIL" if blocking else "PASS",
        "release_blocking": blocking,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    validate_output(package, "zero_trust_evidence_package.schema.yaml")
    return envelope("P0.S4.M05", "evidence_package_builder", INPUTS, {"zero_trust_evidence_package": package})
