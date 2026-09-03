
from collections import defaultdict, deque
from .helpers import yaml_load

def test_same_cycle_module_graph_is_acyclic(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    ids={m['module_id'] for m in io['module_io_matrix']}
    graph={m['module_id']:set(m.get('emits_to',{}).get('modules',[])) for m in io['module_io_matrix']}
    indeg={x:0 for x in ids}
    for src,dsts in graph.items():
        for dst in dsts:
            assert dst in ids
            indeg[dst]+=1
    q=deque([x for x,d in indeg.items() if d==0]); seen=[]
    while q:
        x=q.popleft(); seen.append(x)
        for y in graph[x]:
            indeg[y]-=1
            if indeg[y]==0:q.append(y)
    assert len(seen)==len(ids)

def test_consume_emit_connections_are_reciprocal(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    mm={m['module_id']:m for m in io['module_io_matrix']}
    errors=[]
    for mid,m in mm.items():
        for up in m.get('consumes_from',{}).get('modules',[]):
            if up in mm and mid not in mm[up].get('emits_to',{}).get('modules',[]): errors.append((up,mid))
        for down in m.get('emits_to',{}).get('modules',[]):
            if down in mm and mid not in mm[down].get('consumes_from',{}).get('modules',[]): errors.append((mid,down))
    assert not errors

def test_artifact_registry_has_unique_producers(plan_root):
    reg=yaml_load(plan_root/'contracts'/'INTERNAL_ARTIFACT_REGISTRY.yaml')
    producers=defaultdict(list)
    for row in reg: producers[row['artifact']].append(row['producer'])
    dup={a:p for a,p in producers.items() if len(set(p))!=1}
    assert not dup

def test_artifact_registry_matches_module_outputs(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    output_owner={a:m['module_id'] for m in io['module_io_matrix'] for a in m['emits_to']['artifacts']}
    reg={r['artifact']:r['producer'] for r in yaml_load(plan_root/'contracts'/'INTERNAL_ARTIFACT_REGISTRY.yaml')}
    mismatches={a:(owner,reg.get(a)) for a,owner in output_owner.items() if reg.get(a)!=owner}
    assert not mismatches

def test_temporal_edges_do_not_appear_as_same_cycle_module_backedges(plan_root):
    io=yaml_load(plan_root/'contracts'/'TEMPORAL_EDGES.yaml')
    temporal={(e['from_artifact'],e['to_artifact']) for e in io.get('temporal_edges',[])}
    assert temporal
    for a,b in temporal:
        assert a!=b
        assert 'N+1' in next(e['semantics'] for e in io['temporal_edges'] if e['from_artifact']==a and e['to_artifact']==b) or 'later cycles' in next(e['semantics'] for e in io['temporal_edges'] if e['from_artifact']==a and e['to_artifact']==b)

