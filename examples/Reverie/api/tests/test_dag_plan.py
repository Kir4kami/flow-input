import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dag_plan import (build_plan, deduplicate_plan, find_cross_group_conflicts,
                      refine_groups, schedule_stages)


def make_topology(root, ecmp=False, error="0"):
    path = root / "topology.txt"
    switch_ids = "4 5 6 7" if ecmp else "4 5 6"
    links = [(0,4),(1,4),(2,5),(3,5),(4,6),(5,6)]
    if ecmp: links += [(4,7),(5,7)]
    lines = [f"{8 if ecmp else 7} {4 if ecmp else 3} 2 {len(links)} 25000000000 25000000000", switch_ids]
    lines += [f"{a} {b} 25000000000 2us {error}" for a,b in links]
    path.write_text("\n".join(lines) + "\n")
    return path


def stage(root, name, flows=None, phases=None, operations=None):
    directory = root / "rdma" / name
    directory.mkdir(parents=True)
    if operations is None:
        phases = phases if phases is not None else [flows or [(0,1,1000,1000,32768)]]
        operations = [phases]
    for index, phases in enumerate(operations):
        lines = ["stat rdma operate:"]
        for phase in phases:
            lines.append("phase:1")
            lines += [f"Type rdma_send src_node {src} src_port {sport} dst_node {dst} dst_port {dport} priority 0 msg_len {size}"
                      for src,dst,sport,dport,size in phase]
        (directory / f"rdma_operate{index}.txt").write_text("\n".join(lines) + "\n")
    return {"name":name,"type":"TP","layer":1,"nodes_passed":["FAKE"]}


def plan(root, nodes, edges=(), ecmp=False, **kwargs):
    topology = make_topology(root, ecmp)
    data = {"nodes":[{"name":"Root"},*nodes],"edges":[{"from_node":a,"to_node":b} for a,b in edges]}
    return build_plan(data, root / "rdma", topology, **kwargs)


def test_diamond_preserves_all_parents_and_schedules_join(tmp_path):
    nodes = [stage(tmp_path,n) for n in "ABCD"]
    result = plan(tmp_path,nodes,[("A","B"),("A","C"),("B","D"),("C","D")])
    assert result["stages"][-1]["predecessors"] == ["B","C"]
    assert result["counts"]["logical_unit_count"] == 4
    assert result["counts"]["representative_count"] == 1
    windows = schedule_stages(result,{"A":1,"B":2,"C":5,"D":3})
    assert windows["D"] == {"start_ns":6,"finish_ns":9,"duration_ns":3}


def test_symmetric_effective_network_deduplicates_and_records_mapping(tmp_path):
    a = stage(tmp_path,"A",[(0,1,1000,1000,32768)])
    b = stage(tmp_path,"B",[(2,3,2000,2000,32768)])
    b["type"] = "EP"  # Names and operator labels are not simulation input.
    result = plan(tmp_path,[a,b])
    assert result["counts"]["representative_count"] == 1
    assert result["counts"]["reused_unit_count"] == 1
    mapping = result["representatives"][0]["mappings"]["group2"]
    assert mapping["stage_map"] == {"A":"B"}
    assert mapping["node_map"]["0"] == 2
    assert mapping["node_map"]["1"] == 3
    assert mapping["port_map"] == {"1000":2000}
    assert mapping["operation_map"] == {"A":{"0":0}}
    json.dumps(result)


def test_different_message_sizes_are_not_reused(tmp_path):
    result = plan(tmp_path,[stage(tmp_path,"A"),stage(tmp_path,"B",[(0,1,2000,2000,32769)])])
    assert result["counts"]["representative_count"] == 2


def test_phase_order_and_qp_reuse_relationship_are_input(tmp_path):
    a = stage(tmp_path,"A",phases=[[(0,1,1000,1000,10)],[(0,1,1000,1000,20)]])
    b = stage(tmp_path,"B",phases=[[(0,1,2000,2000,10)],[(0,1,2001,2001,20)]])
    assert plan(tmp_path,[a,b])["counts"]["representative_count"] == 2


def test_ecmp_ports_are_not_normalized_without_a_route_certificate(tmp_path):
    a = stage(tmp_path,"A",[(0,2,1000,1000,10)])
    b = stage(tmp_path,"B",[(0,2,2000,2000,10)])
    assert plan(tmp_path,[a,b],ecmp=True)["counts"]["representative_count"] == 2


def test_literal_identical_ecmp_input_can_be_reused(tmp_path):
    a = stage(tmp_path,"A",[(0,2,1000,1000,10)])
    b = stage(tmp_path,"B",[(0,2,1000,1000,10)])
    assert plan(tmp_path,[a,b],ecmp=True)["counts"]["representative_count"] == 1


def test_operation_dependencies_are_not_dropped(tmp_path):
    phases = [[(0,1,1000,1000,10)]]
    a=stage(tmp_path,"A",operations=[phases,phases])
    b=stage(tmp_path,"B",operations=[phases,phases])
    (tmp_path / "rdma/A/dependence.txt").write_text("1:0\n")
    result = plan(tmp_path,[a,b])
    assert result["counts"]["representative_count"] == 2
    assert result["stages"][0]["operations"][1]["predecessors"] == ["A:op0"]


def test_boundary_release_profile_changes_equivalence(tmp_path):
    result=plan(tmp_path,[stage(tmp_path,"A"),stage(tmp_path,"B")])
    assert result["counts"]["representative_count"] == 1
    assert deduplicate_plan(result,releases={"A":0,"B":10})["counts"]["representative_count"] == 2
    assert deduplicate_plan(result,enabled=False)["counts"]["representative_count"] == 2


def test_touching_windows_do_not_conflict_and_true_overlap_merges(tmp_path):
    result=plan(tmp_path,[stage(tmp_path,"A"),stage(tmp_path,"B")])
    assert find_cross_group_conflicts(result,{"A":[0,10],"B":[10,20]}) == []
    conflicts=find_cross_group_conflicts(result,{"A":[0,11],"B":[10,20]})
    assert conflicts == [("A","B")]
    refined=refine_groups(result,conflicts)
    assert refined["counts"]["group_count"] == 1
    assert refined["groups"][0]["stage_ids"] == ["A","B"]


def test_merge_closes_quotient_cycles(tmp_path):
    result=plan(tmp_path,[stage(tmp_path,n) for n in "ABC"],[("A","B"),("B","C")])
    refined=refine_groups(result,[("A","C")])
    assert refined["counts"]["group_count"] == 1
    assert refined["groups"][0]["stage_ids"] == ["A","B","C"]


def test_stage_cycles_and_unknown_dependencies_are_rejected(tmp_path):
    nodes=[stage(tmp_path,n) for n in "AB"]
    with pytest.raises(ValueError,match="cycle"):
        plan(tmp_path,nodes,[("A","B"),("B","A")])
    with pytest.raises(ValueError,match="unknown"):
        plan(tmp_path,nodes,[("A","missing")])


def test_empty_stage_is_zero_traffic_and_not_random_resource_data(tmp_path):
    a=stage(tmp_path,"A",operations=[])
    b=stage(tmp_path,"B",operations=[])
    result=plan(tmp_path,[a,b])
    assert all(stage["empty"] and not stage["resources"] for stage in result["stages"])
    assert result["counts"]["representative_count"] == 1
    assert schedule_stages(result,{"A":0,"B":0})["B"]["finish_ns"] == 0


def test_more_than_four_representatives_are_allowed(tmp_path):
    nodes=[stage(tmp_path,f"stage{i}",[(0,1,1000,1000,i+1)]) for i in range(7)]
    result=plan(tmp_path,nodes)
    assert result["counts"]["representative_count"] == 7


def test_different_effective_link_parameters_prevent_reuse(tmp_path):
    a=stage(tmp_path,"A",[(0,1,1000,1000,10)])
    b=stage(tmp_path,"B",[(2,3,2000,2000,10)])
    topology=make_topology(tmp_path)
    topology.write_text(topology.read_text().replace("2 5 25000000000 2us", "2 5 10000000000 2us"))
    result=build_plan({"nodes":[a,b],"edges":[]},tmp_path/"rdma",topology)
    assert result["counts"]["representative_count"] == 2


def test_conflict_merge_preserves_transitive_dependencies(tmp_path):
    nodes=[stage(tmp_path,n) for n in "ABCDE"]
    result=plan(tmp_path,nodes,[("A","B"),("B","C"),("C","D"),("D","E")])
    result=refine_groups(result,[("B","D")])
    assert [group["stage_ids"] for group in result["groups"]] == [["A"],["B","C","D"],["E"]]
    assert result["groups"][1]["predecessors"] == ["group1"]
    assert result["groups"][2]["predecessors"] == ["group2"]
