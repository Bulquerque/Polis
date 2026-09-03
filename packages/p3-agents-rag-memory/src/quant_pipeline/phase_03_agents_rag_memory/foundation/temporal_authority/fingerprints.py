from __future__ import annotations
from pathlib import Path
import hashlib, platform, sys
from typing import Any
from .canonical import stable_sha256

def _file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def build_runtime_fingerprints(package_root: Path, *, configs:list[dict[str,Any]], schemas:list[dict[str,Any]], providers:list[dict[str,Any]], prompts:list[dict[str,Any]], seeds:dict[str,Any], budgets:dict[str,Any]) -> dict[str,Any]:
    files={name:_file_hash(package_root/name) for name in ("PACKAGE_MANIFEST.json","FILE_MANIFEST.json","pyproject.toml")}
    aggregates={
      "configs_sha256":stable_sha256([(r["config_id"],r["content_hash"]) for r in configs]),
      "schemas_sha256":stable_sha256([(r["schema_id"],r["content_hash"]) for r in schemas]),
      "providers_sha256":stable_sha256(providers),
      "prompts_sha256":stable_sha256(prompts),
      "seeds_sha256":stable_sha256(seeds),
      "budgets_sha256":stable_sha256(budgets),
    }
    environment={"python":platform.python_version(),"implementation":platform.python_implementation(),"platform":platform.platform()}
    return {"files":files,"aggregates":aggregates,"environment":environment,"environment_sha256":stable_sha256(environment),"authority_sha256":stable_sha256({"files":files,"aggregates":aggregates})}
