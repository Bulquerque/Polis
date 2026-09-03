from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]

def y(path): return yaml.safe_load((ROOT/path).read_text(encoding="utf-8"))

def test_matrix_is_p0_compact_contract_v4():
    m=y("contracts/MODULE_IO_MATRIX.yaml")
    assert set(m)=={"phase","rc","contract","format","module_io_matrix"}
    assert m["phase"]=="P3" and m["rc"]=="RC4.1"
    assert m["contract"]=="MODULE_IO_MATRIX" and m["format"]=="compact_contract_v4"
    assert len(m["module_io_matrix"])==81
    for row in m["module_io_matrix"]:
        assert set(row)=={"module_id","module_name","subphase","consumes_from","emits_to","module_contract"}
        assert set(row["consumes_from"])=={"modules","artifacts","phase_inputs"}
        assert set(row["emits_to"])=={"modules","artifacts","phase_outputs"}
        assert set(row["consumes_from"]["phase_inputs"]) <= set(row["consumes_from"]["artifacts"])
        assert set(row["emits_to"]["phase_outputs"]) <= set(row["emits_to"]["artifacts"])

def test_module_contracts_match_compact_matrix_and_flat_schemas():
    m=y("contracts/MODULE_IO_MATRIX.yaml")
    by={r["module_id"]:r for r in m["module_io_matrix"]}
    for mid,row in by.items():
        c=y(row["module_contract"])
        assert c["module_id"]==mid
        assert c["inputs"]==row["consumes_from"]["artifacts"]
        assert c["outputs"]==row["emits_to"]["artifacts"]
        assert c["allowed_connections"]["consumes_from"]==row["consumes_from"]
        assert c["allowed_connections"]["emits_to"]==row["emits_to"]
        for a in c["outputs"]:
            sp=ROOT/"schemas"/f"{a}.schema.yaml"
            assert sp.is_file(), (mid,a)
            assert (y(sp).get("artifact_name") or y(sp).get("artifact"))==a

def test_connections_reciprocal_and_shared_artifacts():
    rows=y("contracts/MODULE_IO_MATRIX.yaml")["module_io_matrix"]
    by={r["module_id"]:r for r in rows}
    for r in rows:
        for parent in r["consumes_from"]["modules"]:
            if parent in by:
                assert r["module_id"] in by[parent]["emits_to"]["modules"]
                assert set(r["consumes_from"]["artifacts"]) & set(by[parent]["emits_to"]["artifacts"])
        for child in r["emits_to"]["modules"]:
            if child in by:
                assert r["module_id"] in by[child]["consumes_from"]["modules"]
                assert set(r["emits_to"]["artifacts"]) & set(by[child]["consumes_from"]["artifacts"])
