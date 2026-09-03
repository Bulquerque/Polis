from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_04_feature_base.modules import (
    P4_S1_M01_phase2_feature_intake_validator as legacy_alias,
    P4_S1_M01_phase2_handoff_validator as canonical,
)


ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "src" / "quant_pipeline" / "phase_04_feature_base" / "modules"


def test_legacy_alias_is_explicitly_excluded_from_canonical_module_count() -> None:
    canonical_modules = sorted(
        path
        for path in MODULES.glob("P4_S*_M*.py")
        if path.stem != "P4_S1_M01_phase2_feature_intake_validator"
    )
    assert len(canonical_modules) == 49
    assert canonical.MODULE_ID == legacy_alias.MODULE_ID == "P4.S1.M01"
    assert canonical.MODULE_NAME == "phase2_handoff_validator"
    assert legacy_alias.MODULE_NAME == canonical.MODULE_NAME


def test_legacy_alias_declares_canonical_provenance() -> None:
    source = (MODULES / "P4_S1_M01_phase2_feature_intake_validator.py").read_text(
        encoding="utf-8"
    )
    assert "P4_S1_M01_phase2_handoff_validator" in source
    assert "source_path" in source
    assert "generated_at" in source
    assert "generated_by" in source
    assert "requirements_covered" in source
    assert "validation_result" in source
    assert "canonical_filename" in source
