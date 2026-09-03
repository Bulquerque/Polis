from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib
from jsonschema import Draft202012Validator, FormatChecker
import yaml
from .authority import GlobalSchemaAuthority, SchemaAuthorityRecord
from .canonical import ensure_mapping, extract_records, normalize_version, require_fields, require_no_forbidden_fields
from .errors import S1ContractError
from ...shared.assets import source_or_packaged_root

PACKAGE_ROOT = source_or_packaged_root()
CANONICAL_SCHEMA_ROOT = PACKAGE_ROOT / "schemas"
COMMON_ENVELOPE_FIELDS = ("artifact_id", "created_at", "lineage_id", "pipeline_version")
RECORD_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "clean_document_panel": ("document_id","source_id","source_name","document_type","document_title","document_text_or_path","reference_date","available_at","ingested_at","source_quality_score","language","cleaning_status","lineage_id"),
    "source_quality_panel": ("source_id","source_name","source_type","quality_score","readability_status","error_flag","warning_flag","declared_available_at","lineage_id"),
}
DATA_ARTIFACTS=frozenset({"clean_context_source_panel","clean_document_panel","clean_event_reference_panel","source_quality_panel"})
MANIFESTS=frozenset({"context_handoff_manifest","phase3_handoff_manifest"})

def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file(): raise S1ContractError("P3_S1_SCHEMA_MISSING",f"Missing schema: {path}")
    value=yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise S1ContractError("P3_S1_SCHEMA_INVALID",f"Schema must be a mapping: {path}")
    return value

class SchemaRegistry:
    def __init__(self, authority: GlobalSchemaAuthority | None = None) -> None:
        self.authority=authority

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "SchemaRegistry":
        return cls(GlobalSchemaAuthority.from_config(config))

    def _local_path(self, artifact_name: str) -> Path:
        path=CANONICAL_SCHEMA_ROOT/f"{artifact_name}.schema.yaml"
        if not path.is_file(): raise S1ContractError("P3_S1_SCHEMA_MISSING",str(path))
        return path

    def external_path(self, artifact_name: str) -> Path:
        return self.authority.path_for(artifact_name) if self.authority else self._local_path(artifact_name)

    def external(self, artifact_name: str) -> dict[str, Any]:
        return self.authority.load(artifact_name) if self.authority else load_yaml(self._local_path(artifact_name))

    def authority_record(self, artifact_name: str) -> SchemaAuthorityRecord:
        if self.authority: return self.authority.record(artifact_name)
        path=self._local_path(artifact_name)
        return SchemaAuthorityRecord(artifact_name,str(path),hashlib.sha256(path.read_bytes()).hexdigest(),"LOCAL_MIRROR")

    def internal(self, artifact_name: str) -> dict[str, Any]:
        return load_yaml(self._local_path(artifact_name))

    def validate_external(self, artifact_name: str, raw: Any) -> dict[str, Any]:
        value=ensure_mapping(raw,artifact_name); schema=self.external(artifact_name); require_no_forbidden_fields(value,artifact_name)
        schema_forbidden=set(str(x) for x in schema.get("forbidden_fields",[]))
        leaked=sorted(schema_forbidden & set(value))
        if leaked: raise S1ContractError("P3_S1_EXTERNAL_FORBIDDEN_FIELD",f"{artifact_name}: {leaked}")
        if artifact_name in DATA_ARTIFACTS:
            require_fields(value,COMMON_ENVELOPE_FIELDS,location=artifact_name)
            records=extract_records(value,artifact_name)
            for index,row in enumerate(records):
                required=RECORD_REQUIRED_FIELDS.get(artifact_name,())
                if required: require_fields(row,required,location=f"{artifact_name}.records[{index}]")
        elif artifact_name in MANIFESTS:
            require_fields(value,tuple(schema.get("required_fields",())),location=artifact_name)
        else: raise S1ContractError("P3_S1_SCHEMA_UNKNOWN",artifact_name)
        expected=str(schema.get("schema_version","")); observed=str(value.get("pipeline_version",""))
        if expected and normalize_version(expected)!=normalize_version(observed):
            raise S1ContractError("P3_S1_SCHEMA_VERSION_INCOMPATIBLE",f"{artifact_name}: {observed} vs {expected}")
        return value

    def validate_internal(self, artifact_name: str, value: Any) -> None:
        schema=self.internal(artifact_name); validator=Draft202012Validator(schema,format_checker=FormatChecker())
        errors=sorted(validator.iter_errors(value),key=lambda e:list(e.path))
        if errors:
            details=[f"{'/'.join(str(p) for p in e.path) or '$'}: {e.message}" for e in errors[:10]]
            raise S1ContractError("P3_S1_INTERNAL_SCHEMA_INVALID",f"{artifact_name}: {details}")
