from __future__ import annotations


def reason_prefix(module_id: str) -> str:
    if module_id.startswith("P7.S3"):
        return "P7_S3"
    if module_id.startswith("P7.S4"):
        return "P7_S4"
    return "P7_STAGE2"
