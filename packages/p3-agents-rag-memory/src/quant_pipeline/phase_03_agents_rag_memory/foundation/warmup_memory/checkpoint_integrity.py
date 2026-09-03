from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
from typing import Any

class CheckpointIntegrityError(ValueError): pass

def stable_hash(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class CheckpointEnvelope:
    schema_id:str; schema_version:str; checkpoint_id:str; state_schema_version:str; state_hash:str; payload:dict[str,Any]
    def as_dict(self)->dict[str,Any]:
        return {"schema_id":self.schema_id,"schema_version":self.schema_version,"checkpoint_id":self.checkpoint_id,"state_schema_version":self.state_schema_version,"state_hash":self.state_hash,"payload":self.payload}

def build_checkpoint_envelope(payload:dict[str,Any],*,checkpoint_id:str,state_schema_version:str="2.0.0")->dict[str,Any]:
    if not isinstance(payload,dict): raise CheckpointIntegrityError("checkpoint payload must be a mapping")
    return CheckpointEnvelope("p3_checkpoint_envelope.v1","1.0.0",checkpoint_id,state_schema_version,stable_hash(payload),payload).as_dict()

def validate_checkpoint_envelope(value:dict[str,Any],*,accepted_state_versions:tuple[str,...]=( "2.0.0",))->dict[str,Any]:
    required={"schema_id","schema_version","checkpoint_id","state_schema_version","state_hash","payload"}
    if not isinstance(value,dict) or set(value)!=required: raise CheckpointIntegrityError("checkpoint envelope fields invalid")
    if value["schema_id"]!="p3_checkpoint_envelope.v1" or value["schema_version"]!="1.0.0": raise CheckpointIntegrityError("checkpoint envelope version invalid")
    if value["state_schema_version"] not in accepted_state_versions: raise CheckpointIntegrityError("checkpoint state version unsupported")
    if stable_hash(value["payload"])!=value["state_hash"]: raise CheckpointIntegrityError("checkpoint payload corrupted")
    return value
