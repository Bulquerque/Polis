from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s2_identity import DOMAIN_POLICY_VERSION, IDENTITY_POLICY_VERSION, harmonize_record

_REQUIRED_INPUTS = ["pit_normalized_raw_bundle"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    require_inputs(inputs, _REQUIRED_INPUTS)

    rows = records(inputs["pit_normalized_raw_bundle"], "pit_normalized_raw_bundle")
    if not rows:
        raise ContractValidationError("contract_key_deterministic violation: pit bundle is empty")

    harmonized: list[dict] = []
    rejected: list[dict] = []
    seen_observations: set[str] = set()
    public_to_canonical: dict[str, str] = {}

    for row in rows:
        try:
            normalized = harmonize_record(row, config)
        except ContractValidationError as exc:
            if str(row.get("source_category") or "").lower() in {"b3", "bovespa"} and str(row.get("record_domain") or "").upper() in {"OPTION_QUOTE", "OPTION_CONTRACT"} and row.get("underlying") in (None, ""):
                rejected.append({"source_id": row.get("source_id"), "option_id": row.get("option_id"), "reason": "B3_OPTION_UNDERLYING_UNRESOLVED", "detail": str(exc)})
                continue
            raise
        observation = str(normalized["observation_key"])
        if observation in seen_observations:
            raise ContractValidationError(f"P2_S2_M02_DUPLICATE_OBSERVATION_KEY: {observation}")
        seen_observations.add(observation)

        public_key = str(normalized.get("contract_key"))
        canonical_key = normalized.get("canonical_contract_key")
        if canonical_key:
            previous = public_to_canonical.setdefault(public_key, str(canonical_key))
            if previous != str(canonical_key):
                raise ContractValidationError(
                    "P2_S2_M02_LEGACY_CONTRACT_KEY_COLLISION: "
                    f"public_key={public_key} maps to multiple canonical contracts"
                )
        harmonized.append(normalized)

    no_forbidden_rows(harmonized)
    output = artifact(
        "identifier-harmonized-bundle",
        harmonized,
        config,
        contract_key_deterministic=True,
        no_synthetic_instrument=True,
        observation_keys_unique=True,
        identity_policy_version=IDENTITY_POLICY_VERSION,
        domain_policy_version=DOMAIN_POLICY_VERSION,
        unknown_domain_count=sum(row.get("record_domain") == "UNKNOWN" for row in harmonized),
        rejected_record_count=len(rejected),
        rejected_records=rejected,
    )
    return {
        "module_id": "P2.S2.M02",
        "module_name": "identifier_key_harmonizer",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S2",
        "contract": "P2_S2_M02_identifier_key_harmonizer.yaml",
        "required_inputs": _REQUIRED_INPUTS,
        "outputs": {"identifier_harmonized_bundle": output},
    }
