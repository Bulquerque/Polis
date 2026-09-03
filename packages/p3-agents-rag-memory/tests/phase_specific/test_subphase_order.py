import yaml


def y(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_subphase_canonical_order_respects_local_dependencies(plan_root):
    io = y(plan_root / "contracts" / "MODULE_IO_MATRIX.yaml")
    by = {m["module_id"]: m for m in io["module_io_matrix"]}
    for p in (plan_root / "tests" / "specifications" / "subphases").glob("*.yaml"):
        s = y(p)
        order = s["canonical_module_order"]
        pos = {x: i for i, x in enumerate(order)}
        for mid in order:
            for dep in by[mid].get("consumes_from", {}).get("modules", []):
                if dep in pos:
                    assert pos[dep] < pos[mid], (s["subphase"], dep, mid)
