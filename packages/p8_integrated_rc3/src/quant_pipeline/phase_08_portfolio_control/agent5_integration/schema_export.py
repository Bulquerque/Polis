from __future__ import annotations
import json
from pathlib import Path
from .models import Agent5IntegratedRequest, Agent5IntegratedResult
MODELS={"agent5_integrated_request":Agent5IntegratedRequest,"agent5_integrated_result":Agent5IntegratedResult}
def export_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True,exist_ok=True); written=[]
    for name,model in MODELS.items():
        schema=model.model_json_schema(mode="validation")
        schema["$schema"]="https://json-schema.org/draft/2020-12/schema"
        schema["$id"]=f"https://inferencia.local/schemas/p8/agent5/{name}.schema.json"
        path=directory/f"{name}.schema.json"
        path.write_text(json.dumps(schema,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        written.append(path)
    return tuple(written)
