from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from .canonical import stable_sha256
from .errors import S2ContractError

class CanaryProbePort(Protocol):
    def probe(self, *, provider_id:str, model_id:str, prompt:str) -> str: ...

@dataclass(frozen=True, slots=True)
class CanaryResult:
    canary_id:str; status:str; response_hash:str; matched_markers:tuple[str,...]
    def as_dict(self)->dict[str,Any]: return {"canary_id":self.canary_id,"status":self.status,"response_hash":self.response_hash,"matched_markers":list(self.matched_markers)}

def run_canary_suite(provider_id:str, model_id:str, suite:dict[str,Any], probe:CanaryProbePort) -> dict[str,Any]:
    rows=[]
    for canary in suite.get("canaries",[]):
        response=str(probe.probe(provider_id=provider_id,model_id=model_id,prompt=str(canary["prompt"])))
        markers=tuple(sorted(m for m in canary.get("contamination_markers",[]) if m in response))
        rows.append(CanaryResult(str(canary["canary_id"]),"DETECTED" if markers else "PASS",stable_sha256(response),markers).as_dict())
    if not rows: raise S2ContractError("P3_S2_M03_CANARY_SUITE_EMPTY","No canaries configured")
    status="DETECTED" if any(r["status"]=="DETECTED" for r in rows) else "PASS"
    return {"suite_id":str(suite.get("suite_id","unknown")),"suite_version":str(suite.get("suite_version","unknown")),"suite_hash":stable_sha256(suite),"status":status,"results":rows}
