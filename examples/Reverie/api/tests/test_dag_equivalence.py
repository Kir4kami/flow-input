"""Counterexamples for generic input equivalence and its validation gate."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dag_plan import build_plan, deduplicate_plan, match_groups
import dag_plan


def make_plan(root, workloads, edges=(), groups=None, ecmp=False):
    topology = root/'topology.txt'
    links = [(0,4),(1,4),(2,5),(3,5),(4,6),(5,6)]
    if ecmp: links += [(4,7),(5,7)]
    topology.write_text(f'{8 if ecmp else 7} {4 if ecmp else 3} 2 {len(links)} 25000000000 25000000000\n'
        + ('4 5 6 7\n' if ecmp else '4 5 6\n')
        + ''.join(f'{a} {b} 25000000000 2us 0\n' for a,b in links))
    for name,ops in workloads.items():
        directory = root/'rdma'/name;directory.mkdir(parents=True)
        for index,phases in enumerate(ops):
            text='stat rdma operate:\n'
            for phase in phases:
                text+='phase:0\n'
                for src,dst,port,size in phase:
                    text+=f'Type rdma_send src_node {src} src_port {port} dst_node {dst} dst_port {port} priority 0 msg_len {size}\n'
            (directory/f'rdma_operate{index}.txt').write_text(text)
    return build_plan({'nodes':[{'name':name,'type':'arbitrary_label'} for name in workloads],
                       'edges':[{'from':a,'to':b} for a,b in edges]},root/'rdma',topology,groups=groups)


def native(plan, entries):
    result=deepcopy(plan)
    peers={node['id']:[] for node in plan['topology']['nodes']}
    for link in plan['topology']['links']:
        peers[link['src']].append(link['dst']);peers[link['dst']].append(link['src'])
    def hops(path):
        result=[]
        for a,b in zip(path,path[1:]):
            out_if=sorted(peers[a]).index(b)+1
            entry={'node':a,'next_node':b,'out_if':out_if,'in_if':sorted(peers[b]).index(a)+1,
                   'next_hop_out_ifs':[out_if],'hash_algorithm':'ns3::Hash32' if a < 4 else 'SwitchNode::EcmpHash'}
            if a >= 4: entry['ecmp_seed']=a
            result.append(entry)
        return result
    result['route_certificate']={'schema_version':1,'certified':True,'oracle':'native',
        'experiment_fingerprint':plan['experiment_fingerprint'],'native_binary_sha256':'test-binary',
        'native_runtime_sha256':'test-runtime-and-libraries',
        'topology_fingerprint':hashlib.sha256(json.dumps(plan['topology'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
        'protocol_coverage':{'data':[17],'reverse':[252,253]},
        'routes':{key:{'forward':forward,'reverse':reverse,'forward_hops':hops(forward),'reverse_hops':hops(reverse)}
                  for key,forward,reverse in entries}}
    return result


def test_phase_flow_permutation_is_a_candidate_only_and_has_complete_maps(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,1,1000,10),(2,3,1001,20)]]],
                             'B':[[[(2,3,2001,20),(0,1,2000,10)]]]})
    assert plan['counts']['representative_count']==2
    candidate=deduplicate_plan(plan,allow_provisional=True)
    assert candidate['counts']['representative_count']==1
    mapping=candidate['representatives'][0]['mappings']['group2']
    assert mapping['verification_required'] and mapping['equivalence_status']=='provisional'
    assert mapping['operation_map']=={'A':{'0':0}}
    assert mapping['phase_map']=={'A':{'0':{'0':0}}}
    assert mapping['flow_map']=={'A':{'0':{'0':{'0':1,'1':0}}}}
    assert mapping['port_map']=={'1000':2000,'1001':2001}
    assert candidate['deduplication']['requires_mode_validation']
    assert deduplicate_plan(candidate,allow_provisional=False)['counts']['representative_count']==2
    json.dumps(candidate)


def test_shared_source_launch_order_cannot_be_permuted_even_as_candidate(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,1,1000,10),(0,2,1001,20)]]],
                             'B':[[[(0,2,2001,20),(0,1,2000,10)]]]})
    assert deduplicate_plan(plan,allow_provisional=True)['counts']['representative_count']==2


def test_shared_data_egress_order_cannot_be_permuted(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,2,1000,10),(1,2,1001,20)]]],
                             'B':[[[(1,2,2001,20),(0,2,2000,10)]]]})
    assert deduplicate_plan(plan,allow_provisional=True)['counts']['representative_count']==2


def test_independent_operation_permutation_is_generic_and_provisional(tmp_path):
    plan=make_plan(tmp_path,{'first':[[[(0,1,1000,10)]],[[(2,3,1001,20)]]],
                             'second':[[[(2,3,2001,20)]],[[(0,1,2000,10)]]]})
    assert plan['counts']['representative_count']==2
    candidate=deduplicate_plan(plan,allow_provisional=True)
    assert candidate['counts']['representative_count']==1
    mapping=candidate['representatives'][0]['mappings']['group2']
    assert mapping['operation_map']=={'first':{'0':1,'1':0}}
    assert mapping['verification_required']


def test_phase_order_remains_semantic(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,1,1000,10)],[(0,1,1000,20)]]],
                             'B':[[[(0,1,2000,20)],[(0,1,2000,10)]]]})
    assert deduplicate_plan(plan,allow_provisional=True)['counts']['representative_count']==2


def test_certified_ecmp_can_normalize_ports_with_equal_data_and_ack_paths(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,2,1000,10)]]],'B':[[[(0,2,2000,10)]]]},ecmp=True)
    assert plan['counts']['representative_count']==2
    plan=native(plan,[('0,2,1000,1000',[0,4,6,5,2],[2,5,6,4,0]),
                      ('0,2,2000,2000',[0,4,6,5,2],[2,5,6,4,0])])
    result=deduplicate_plan(plan)
    assert result['counts']['representative_count']==1
    assert result['equivalence_context']['native_binary_sha256']=='test-binary'
    assert result['equivalence_context']['native_runtime_sha256']=='test-runtime-and-libraries'


def test_different_ack_resources_reject_equal_forward_routes(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,2,1000,10)]]],'B':[[[(0,2,2000,10)]]]},ecmp=True)
    plan=native(plan,[('0,2,1000,1000',[0,4,6,5,2],[2,5,6,4,0]),
                      ('0,2,2000,2000',[0,4,6,5,2],[2,5,7,4,0])])
    assert deduplicate_plan(plan,allow_provisional=True)['counts']['representative_count']==2


def test_stale_native_certificate_cannot_enable_ecmp_reuse(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,2,1000,10)]]],'B':[[[(0,2,2000,10)]]]},ecmp=True)
    plan=native(plan,[('0,2,1000,1000',[0,4,6,5,2],[2,5,6,4,0]),
                      ('0,2,2000,2000',[0,4,6,5,2],[2,5,6,4,0])])
    plan['route_certificate']['experiment_fingerprint']='different-experiment'
    assert deduplicate_plan(plan,allow_provisional=True)['counts']['representative_count']==2


def test_merged_groups_require_complete_identical_relative_boundary_profiles(tmp_path):
    workloads={'A':[[[(0,1,1000,10)]]],'B':[[[(0,1,1001,20)]]],
               'C':[[[(2,3,2000,10)]]],'D':[[[(2,3,2001,20)]]]}
    plan=make_plan(tmp_path,workloads,edges=[('A','B'),('C','D')],groups=[['A','B'],['C','D']])
    assert plan['counts']['representative_count']==2
    assert match_groups(plan,*plan['groups']) is None
    releases={'A':0,'B':10,'C':0,'D':10}
    mapping=match_groups(plan,*plan['groups'],releases)
    assert mapping['stage_map']=={'A':'C','B':'D'}
    assert deduplicate_plan(plan,releases=releases)['counts']['representative_count']==1
    releases['D']=11
    assert match_groups(plan,*plan['groups'],releases,allow_provisional=True) is None


def test_event_order_candidates_are_never_carried_to_another_mode_by_default(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,1,1000,10),(2,3,1001,20)]]],
                             'B':[[[(2,3,2001,20),(0,1,2000,10)]]]})
    candidate=deduplicate_plan(plan,allow_provisional=True)
    candidate['equivalence_mode']='mixed'
    strict=deduplicate_plan(candidate)
    assert strict['counts']['representative_count']==2
    assert strict['equivalence_context']['mode']=='mixed'
    assert not strict['deduplication']['requires_mode_validation']


def test_exhausted_total_search_budget_keeps_remaining_units_independent(tmp_path,monkeypatch):
    plan=make_plan(tmp_path,{name:[[[(0,1,1000,10)]]] for name in ('A','B','C')})
    assert plan['counts']['representative_count']==1
    ticks=iter(range(0,1000,20))
    monkeypatch.setattr(dag_plan,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    result=deduplicate_plan(plan,allow_provisional=True)
    assert result['counts']['representative_count']==3
    assert result['deduplication']['search_budget_exhausted']


@pytest.mark.parametrize('value',[-1,0.5,True])
def test_relative_releases_cannot_be_rounded_or_coerced(tmp_path,value):
    plan=make_plan(tmp_path,{'A':[[[(0,1,1000,10)]]]})
    with pytest.raises(ValueError,match='exact nonnegative integer'):
        deduplicate_plan(plan,releases={'A':value})


def test_native_route_certificate_without_library_runtime_binding_is_not_used(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,2,1000,10)]]],'B':[[[(0,2,2000,10)]]]},ecmp=True)
    plan=native(plan,[('0,2,1000,1000',[0,4,6,5,2],[2,5,6,4,0]),
                      ('0,2,2000,2000',[0,4,6,5,2],[2,5,6,4,0])])
    del plan['route_certificate']['native_runtime_sha256']
    assert deduplicate_plan(plan)['counts']['representative_count']==2


def test_packet_host_port_symmetry_requires_a_separate_mixed_witness(tmp_path):
    plan=make_plan(tmp_path,{'A':[[[(0,1,1000,10)]]],'B':[[[(2,3,2000,10)]]]})
    packet=deduplicate_plan(plan,mode='packet')
    mapping=packet['representatives'][0]['mappings']['group2']
    assert not mapping['verification_required']
    assert mapping['mixed_verification_required']
    assert mapping['equivalence_status']=='proven'
    mixed=deduplicate_plan(packet,mode='mixed')
    assert mixed['counts']['representative_count']==2
    assert match_groups(plan,*plan['groups'],mode='mixed') is None
    candidate=deduplicate_plan(packet,mode='mixed',allow_provisional=True)
    assert candidate['counts']['representative_count']==1
    mapping=candidate['representatives'][0]['mappings']['group2']
    assert mapping['equivalence_status']=='provisional'
    assert mapping['proof_mode']=='mixed'
    assert not mapping['verification_required'] and mapping['mixed_verification_required']


def test_literal_mixed_inputs_can_reuse_across_stage_labels(tmp_path):
    plan=make_plan(tmp_path,{'unrelated_name':[[[(0,1,1000,10)]]],'another_label':[[[(0,1,1000,10)]]]})
    mixed=deduplicate_plan(plan,mode='mixed')
    assert mixed['counts']['representative_count']==1
    assert mixed['representatives'][0]['equivalence_status']=='proven'
    assert not mixed['representatives'][0]['mixed_verification_required']


@pytest.mark.parametrize('damage',['unhashable_path','missing_reverse_protocol','missing_next_hop_vector'])
def test_malformed_native_evidence_falls_back_to_literal_inputs(tmp_path,damage):
    plan=make_plan(tmp_path,{'A':[[[(0,2,1000,10)]]],'B':[[[(0,2,2000,10)]]]},ecmp=True)
    plan=native(plan,[('0,2,1000,1000',[0,4,6,5,2],[2,5,6,4,0]),
                      ('0,2,2000,2000',[0,4,6,5,2],[2,5,6,4,0])])
    if damage=='unhashable_path': plan['route_certificate']['routes']['0,2,1000,1000']['forward'][1]={}
    elif damage=='missing_reverse_protocol': plan['route_certificate']['protocol_coverage']['reverse']=[252]
    else: del plan['route_certificate']['routes']['0,2,1000,1000']['forward_hops'][0]['next_hop_out_ifs']
    result=deduplicate_plan(plan,allow_provisional=True)
    assert result['counts']['representative_count']==2
    assert result['deduplication']['route_certificate_status']=='unique_or_literal'
