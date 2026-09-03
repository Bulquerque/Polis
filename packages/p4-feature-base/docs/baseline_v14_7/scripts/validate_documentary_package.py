#!/usr/bin/env python3
from pathlib import Path
import ast,csv,sys,yaml
ROOT=Path(__file__).resolve().parents[1]

def load_yaml(rel):
    return yaml.safe_load((ROOT/rel).read_text(encoding="utf-8"))

def main():
    errors=[]
    cat=load_yaml("contracts/MODULE_CATALOG.yaml")["modules"]
    io=load_yaml("contracts/MODULE_IO_MATRIX.yaml")["module_io_matrix"]
    outputs=load_yaml("contracts/OUTPUT_CONTRACTS.yaml")
    families=load_yaml("registries/VARIABLE_FAMILY_REGISTRY.yaml")
    encoder=load_yaml("registries/ENCODER_SEARCH_SPACE.yaml")
    ids=[m["module_id"] for m in cat]
    if len(cat)!=49: errors.append(f"expected 49 modules, got {len(cat)}")
    if len(ids)!=len(set(ids)): errors.append("duplicate module ids")
    if len(io)!=len(cat): errors.append("I/O matrix size differs from catalog")
    expected_agent={1:"IMPLEMENTATION_STREAM",2:"IMPLEMENTATION_STREAM",3:"IMPLEMENTATION_STREAM",4:"IMPLEMENTATION_STREAM",5:"IMPLEMENTATION_STREAM",6:"IMPLEMENTATION_STREAM",7:"IMPLEMENTATION_STREAM",8:"IMPLEMENTATION_STREAM",9:"IMPLEMENTATION_STREAM"}
    for module in cat:
        subphase_number=int(module["subphase"].split("S")[1])
        if module.get("implementation_owner")!=expected_agent[subphase_number]:
            errors.append(f"wrong owner {module['module_id']}")
        if not (ROOT/module["contract_file"]).exists():
            errors.append("missing "+module["contract_file"])
    produced={}
    for row in io:
        for artifact in row["emits_artifacts"]:
            if artifact in produced: errors.append(f"duplicate producer {artifact}")
            produced[artifact]=row["module_id"]
    covered=set(produced)|set(outputs.get("artifact_aliases",{}))
    missing=set(outputs["legacy_compatible_required_outputs"])-covered
    if missing: errors.append("legacy outputs missing "+str(sorted(missing)))
    if families.get("family_count")!=10: errors.append("expected 10 families")
    if encoder.get("role")!="OPTIONAL_CHALLENGER" or encoder.get("maximum_sampled_configurations")!=2:
        errors.append("encoder budget must equal 2")
    for path in ROOT.rglob("*.yaml"):
        if "legacy_reference" in path.parts: continue
        try: yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc: errors.append(f"YAML parse {path.relative_to(ROOT)}: {exc}")
    with (ROOT/"registries/FOUNDATIONAL_HYPOTHESIS_CORE_32.csv").open(encoding="utf-8") as handle:
        hypotheses=list(csv.DictReader(handle))
    if len(hypotheses)!=32: errors.append(f"expected 32 hypotheses, got {len(hypotheses)}")
    passports=list((ROOT/"hypothesis_passports").glob("*.yaml"))
    if len(passports)!=32: errors.append(f"expected 32 passports, got {len(passports)}")
    agent_candidates = [ROOT / "AGENT_REGISTRY.csv", ROOT / "registries/AGENT_REGISTRY.csv", ROOT / "agents/AGENT_REGISTRY.csv"]
    agent_path = next((p for p in agent_candidates if p.exists()), None)
    agents = []
    if agent_path:
        with agent_path.open(encoding="utf-8", newline="") as handle:
            agents = list(csv.DictReader(handle))
    else:
        errors.append("missing agent registry")
    if len(agents) != 3: errors.append(f"expected 3 agents, got {len(agents)}")
    all_subphases=[]
    for agent in agents:
        owned=str(agent.get("subphases", "")).split("|")
        if len(owned)!=3: errors.append(f"agent must own 3 subphases: {agent.get('agent_id')}")
        all_subphases.extend(owned)
    if sorted(all_subphases)!=[f"P4.S{i}" for i in range(1,10)]:
        errors.append("subphase ownership incomplete or duplicated")
    ownership_candidates = [ROOT / "MODULE_OWNERSHIP.csv", ROOT / "registries/MODULE_OWNERSHIP.csv", ROOT / "contracts/MODULE_OWNERSHIP.csv"]
    ownership_path = next((p for p in ownership_candidates if p.exists()), None)
    ownership = []
    if ownership_path:
        with ownership_path.open(encoding="utf-8", newline="") as handle:
            ownership = list(csv.DictReader(handle))
    else:
        errors.append("missing module ownership registry")
    if len(ownership)!=49: errors.append(f"expected 49 ownership rows, got {len(ownership)}")
    if any(row.get("execution_stage")=="post_handoff_qualification" and row.get("module_id")!="P4.S9.M05" for row in io):
        errors.append("unexpected post-handoff module")
    required=["P0_P4_CODE_QUALITY_CLOSURE.md","SUBPHASE_IMPLEMENTATION_ROADMAP.md","INTERNAL_CONTRACTS.md","DEBUGGABILITY_OBSERVABILITY_AND_RESOURCE_STANDARD.md","SUBPHASES.md","MODULE_BREAKDOWN.md","TESTING_AND_QUALIFICATION_PLAN.md","contracts/CODE_QUALITY_POLICY.yaml","contracts/ERROR_AND_DIAGNOSTICS_STANDARD.yaml"]
    for rel in required:
        if not (ROOT/rel).exists(): errors.append("missing quality artifact "+rel)
    for path in (ROOT/"scripts").glob("*.py"):
        try: ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        except Exception as exc: errors.append(f"Python parse {path.name}: {exc}")
    if errors:
        print("DOCUMENTARY STATIC VALIDATION: FAIL")
        for error in errors: print("-",error)
        return 1
    print("DOCUMENTARY STATIC VALIDATION: PASS")
    print(f"subphases=9 modules={len(cat)} agents={len(agents)} subphases_per_agent=3 families=10 hypotheses={len(hypotheses)} encoder_configs=2")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
