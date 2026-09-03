from __future__ import annotations
import hashlib,json
from typing import Any

class ResourceAuthorityError(ValueError): pass

def stable_hash(value:Any)->str: return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def rag_signature(config:dict[str,Any],*,embedding_provider_id:str,embedding_model_id:str,embedding_model_version:str,embedding_dimension:int)->dict[str,Any]:
    payload={"index_format_version":config["index_format_version"],"tokenizer_id":config["tokenizer"]["tokenizer_id"],"tokenizer_version":config["tokenizer"]["tokenizer_version"],"chunk_id_algorithm":config["chunking"]["chunk_id_algorithm"],"chunking_policy_version":config["chunking"]["chunking_policy_version"],"embedding_provider_id":embedding_provider_id,"embedding_model_id":embedding_model_id,"embedding_model_version":embedding_model_version,"embedding_dimension":embedding_dimension}
    return {**payload,"signature_sha256":stable_hash(payload)}

def validate_incremental_rebuild(previous:dict[str,Any],current:dict[str,Any],fields:list[str])->dict[str,Any]:
    mismatches=[f for f in fields if previous.get(f)!=current.get(f)]
    if mismatches: raise ResourceAuthorityError(f"incompatible index rebuild:{mismatches}")
    return {"status":"PASS","checked_fields":fields}

def validate_temporal_graph_record(record:dict[str,Any],ontology:dict[str,Any],*,as_of_time:str)->dict[str,Any]:
    missing=[f for f in ontology["required_temporal_fields"] if f not in record]
    if missing: raise ResourceAuthorityError(f"temporal graph fields missing:{missing}")
    if record.get("node_type") and record["node_type"] not in ontology["node_types"]: raise ResourceAuthorityError("unknown graph node type")
    if record.get("edge_type") and record["edge_type"] not in ontology["edge_types"]: raise ResourceAuthorityError("unknown graph edge type")
    if str(record["available_at"])>str(as_of_time): raise ResourceAuthorityError("future graph record")
    return {"status":"PASS"}

def validate_tool_schema_lock(registry:dict[str,Any],lock:dict[str,Any])->dict[str,Any]:
    registered={x["tool_id"]:x for x in registry.get("tools",[])}; locked={x["tool_id"]:x for x in lock.get("tools",[])}
    if set(registered)!=set(locked): raise ResourceAuthorityError("tool lock membership mismatch")
    for tool_id,tool in registered.items():
        row=locked[tool_id]
        if tool.get("tool_version")!=row.get("tool_version"): raise ResourceAuthorityError(f"tool version mismatch:{tool_id}")
        if stable_hash(tool["request_schema"])!=row["request_schema_sha256"]: raise ResourceAuthorityError(f"request schema mismatch:{tool_id}")
        if stable_hash(tool["response_schema"])!=row["response_schema_sha256"]: raise ResourceAuthorityError(f"response schema mismatch:{tool_id}")
    if lock.get("default_decision")!="DENY" or lock.get("deny_overrides") is not True: raise ResourceAuthorityError("deny-by-default lock invalid")
    return {"status":"PASS","tool_count":len(registered)}

def resolve_entitlement(*,allow_rules:list[str],deny_rules:list[str],revoked:bool)->str:
    if revoked or deny_rules: return "DENY"
    return "ALLOW" if allow_rules else "DENY"
