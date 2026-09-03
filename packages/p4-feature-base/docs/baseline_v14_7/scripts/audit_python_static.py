#!/usr/bin/env python3
from pathlib import Path
import ast,json
ROOT=Path(__file__).resolve().parents[1]

def main():
    findings=[]
    files=[]
    risky_names={"eval","exec","compile","__import__"}
    risky_attrs={("os","system"),("subprocess","run"),("subprocess","Popen"),("subprocess","call")}
    for path in ROOT.rglob("*.py"):
        if "legacy_reference" in path.parts or path.name==Path(__file__).name:
            continue
        files.append(path)
        try: tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        except Exception as exc:
            findings.append({"file":str(path.relative_to(ROOT)),"severity":"PARSE_ERROR","detail":str(exc)})
            continue
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call): continue
            if isinstance(node.func,ast.Name) and node.func.id in risky_names:
                findings.append({"file":str(path.relative_to(ROOT)),"severity":"HIGH","detail":f"call {node.func.id} at line {node.lineno}"})
            if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and (node.func.value.id,node.func.attr) in risky_attrs:
                findings.append({"file":str(path.relative_to(ROOT)),"severity":"HIGH","detail":f"call {node.func.value.id}.{node.func.attr} at line {node.lineno}"})
    print(json.dumps({"active_files_scanned":len(files),"findings":findings},ensure_ascii=False,indent=2))
    return 1 if any(item["severity"] in {"HIGH","PARSE_ERROR"} for item in findings) else 0

if __name__ == "__main__":
    raise SystemExit(main())
