from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "integration" / "new_version_sanitized" / "apply_authority_and_runtime_migration.py"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_migration_script_compiles_and_uses_repository_manifest_builders() -> None:
    text = source()
    ast.parse(text)
    assert "tools/regenerate_package_manifests.py" in text
    assert "tools/build_root_manifest.py" in text


def test_backups_are_unique_and_outside_the_repository() -> None:
    text = source()
    assert "%Y%m%dT%H%M%S%fZ" in text
    assert 'root.parent/".p3_authority_backups"/root.name/stamp' in text
    assert 'root/".p3_authority_backups"' not in text


def test_migration_is_reversible_and_fail_closed() -> None:
    text = source()
    assert "migration_manifest.json" in text
    assert "def rollback(" in text
    assert 'if result["status"]!="PASS":raise RuntimeError(result)' in text


def test_migration_skips_self_copy_for_installed_authority_mirrors() -> None:
    text = source()
    assert "source.resolve() == target.resolve()" in text


def test_installer_uses_root_relative_content_hash_exclusions() -> None:
    installer = (ROOT / "integration" / "new_version_sanitized" / "install_phase3.py").read_text(encoding="utf-8")
    assert "relative.as_posix() in CONTENT_EXCLUDED" in installer
    assert "path.name in CONTENT_EXCLUDED" not in installer


def test_installer_requires_exact_installed_release_content_hash() -> None:
    installer = (ROOT / "integration" / "new_version_sanitized" / "install_phase3.py").read_text(encoding="utf-8")
    assert "package_content_sha256(target)" in installer
    assert "installed Phase 3 content does not match the source release" in installer
