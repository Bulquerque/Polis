from __future__ import annotations
import copy
from typing import Any

class ReplayStateMigrationError(ValueError): pass

def migrate_replay_state(value:dict[str,Any],*,target_version:str="2.0.0")->dict[str,Any]:
    if not isinstance(value,dict): raise ReplayStateMigrationError("replay state must be a mapping")
    source=str(value.get("schema_version",""))
    if source==target_version: return copy.deepcopy(value)
    if source!="1.0.0" or target_version!="2.0.0": raise ReplayStateMigrationError(f"unsupported replay migration:{source}->{target_version}")
    out=copy.deepcopy(value); out["schema_version"]="2.0.0"; out.setdefault("migration_lineage",[])
    out["migration_lineage"]=[*out["migration_lineage"],{"migration_id":"replay-state-v1-to-v2","from_version":"1.0.0","to_version":"2.0.0"}]
    out.setdefault("belief_state",{"records":[],"content_hash":None})
    out.setdefault("memory_state",{"records":[],"content_hash":None})
    out.setdefault("social_graph",{"records":[],"content_hash":None})
    return out
