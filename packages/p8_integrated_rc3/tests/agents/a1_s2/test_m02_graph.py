
from quant_pipeline.phase_08_contracts.enums import PositionSide
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import ExposureRelationType
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def _relations(result):
    return [edge.relation for edge in result.m02.exposure_graph.edges]


def test_graph_contains_typed_nodes_and_edges():
    bundle,context=build_input()
    graph=run_s2(S2RunRequest(bundle,context)).m02.exposure_graph
    assert any(node.node_id=="candidate:cand-1" for node in graph.nodes)
    assert ExposureRelationType.CANDIDATE_HAS_LEG in _relations(run_s2(S2RunRequest(bundle,context)))


def test_same_instrument_and_opposite_leg_edges():
    specs=(CandidateSpec("a",1,instrument_id="X",side=PositionSide.LONG),CandidateSpec("b",2,instrument_id="X",side=PositionSide.SHORT))
    bundle,context=build_input(specs)
    rel=_relations(run_s2(S2RunRequest(bundle,context)))
    assert ExposureRelationType.SAME_INSTRUMENT in rel
    assert ExposureRelationType.OPPOSITE_LEG in rel


def test_graph_is_deterministic_under_candidate_input_permutation():
    a=CandidateSpec("a",1,instrument_id="X");b=CandidateSpec("b",2,instrument_id="Y")
    b1,c1=build_input((a,b));b2,c2=build_input((b,a))
    g1=run_s2(S2RunRequest(b1,c1)).m02.exposure_graph
    g2=run_s2(S2RunRequest(b2,c2)).m02.exposure_graph
    assert g1==g2


def test_components_partition_nodes():
    bundle,context=build_input((CandidateSpec("a",1,group_id="g1",instrument_id="X",objective_family="O1",underlying="A"),CandidateSpec("b",1,group_id="g2",instrument_id="Y",objective_family="O2",underlying="B")))
    graph=run_s2(S2RunRequest(bundle,context)).m02.exposure_graph
    flat=[node for comp in graph.connected_components for node in comp.node_ids]
    assert sorted(flat)==sorted(node.node_id for node in graph.nodes)
