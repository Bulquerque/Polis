from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
from typing import Any
import yaml
from .errors import S1ContractError

@dataclass(frozen=True, slots=True)
class SchemaAuthorityRecord:
    artifact_name: str
    path: str
    sha256: str
    authority: str

class GlobalSchemaAuthority:
    def __init__(self, schema_root: Path, *, authority: str = "GLOBAL_REPOSITORY") -> None:
        self.schema_root = schema_root.resolve()
        self.authority = authority
        if not self.schema_root.is_dir():
            raise S1ContractError("P3_S1_GLOBAL_SCHEMA_ROOT_MISSING", str(self.schema_root))

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "GlobalSchemaAuthority | None":
        config = config or {}
        raw = config.get("global_schema_root")
        if raw in (None, ""):
            return None
        return cls(Path(str(raw)))

    def path_for(self, artifact_name: str) -> Path:
        path = self.schema_root / f"{artifact_name}.schema.yaml"
        if not path.is_file():
            raise S1ContractError("P3_S1_GLOBAL_SCHEMA_MISSING", f"{artifact_name}: {path}")
        return path

    def load(self, artifact_name: str) -> dict[str, Any]:
        path = self.path_for(artifact_name)
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise S1ContractError("P3_S1_GLOBAL_SCHEMA_INVALID", str(path))
        return value

    def record(self, artifact_name: str) -> SchemaAuthorityRecord:
        path = self.path_for(artifact_name)
        return SchemaAuthorityRecord(
            artifact_name=artifact_name,
            path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            authority=self.authority,
        )
