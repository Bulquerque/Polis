from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
import yaml

class PopulationAuthorityError(ValueError): pass

def _yaml(path:Path)->dict[str,Any]:
    value=yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise PopulationAuthorityError(f"mapping required: {path}")
    return value

def _sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_population_authority(root:Path)->dict[str,Any]:
    lock=_yaml(root/"config/population/POPULATION_GENERATION_AUTHORITY.yaml")
    issues=[]
    for row in lock.get("files",[]):
        path=root/str(row["path"])
        if not path.is_file(): issues.append(f"missing:{row['path']}"); continue
        if _sha(path)!=row.get("sha256"): issues.append(f"hash_mismatch:{row['path']}")
    if issues: raise PopulationAuthorityError(";".join(issues))
    return {"status":"PASS","authority_id":lock["authority_id"],"file_count":len(lock.get("files",[]))}

def validate_coverage_convergence(config:dict[str,Any])->dict[str,Any]:
    required=("coverage_epsilon","patience_rounds","minimum_novelty_rounds","target_population_size","max_generation_rounds","minimum_coverage_ratio","minimum_density_sufficiency_ratio")
    missing=[x for x in required if x not in config]
    if missing: raise PopulationAuthorityError(f"missing convergence fields: {missing}")
    if not 0 < float(config["coverage_epsilon"]) <= 0.25: raise PopulationAuthorityError("coverage_epsilon out of range")
    if int(config["patience_rounds"]) < 1 or int(config["minimum_novelty_rounds"]) < 1: raise PopulationAuthorityError("round controls must be positive")
    if int(config["max_generation_rounds"]) < int(config["patience_rounds"]): raise PopulationAuthorityError("max rounds below patience")
    if int(config["target_population_size"]) < 1: raise PopulationAuthorityError("target population must be positive")
    for key in ("minimum_coverage_ratio","minimum_density_sufficiency_ratio"):
        if not 0 <= float(config[key]) <= 1: raise PopulationAuthorityError(f"{key} out of range")
    return {"status":"PASS","convergence_contract":"coverage-convergence.1.0.0"}

def validate_graph_calibration(metrics:dict[str,Any],profile:dict[str,Any])->dict[str,Any]:
    failures=[]
    for name,bounds in profile.get("required_ranges",{}).items():
        if name not in metrics: failures.append(f"missing:{name}"); continue
        value=float(metrics[name]); lo=float(bounds["minimum"]); hi=float(bounds["maximum"])
        if not lo <= value <= hi: failures.append(f"out_of_range:{name}:{value}")
    if failures: raise PopulationAuthorityError(";".join(failures))
    return {"status":"PASS","calibration_id":profile["calibration_id"],"metric_count":len(profile.get("required_ranges",{}))}
