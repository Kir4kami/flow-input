import json
from copy import deepcopy
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

REVERIE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REVERIE))
from api.dag_plan import build_plan, deduplicate_plan, refine_groups
from api.dag_runner import (DagCancelled, DagExecutionError, compare_results,
                            run_dag_simulation, run_packet_baseline, _Runner)
from api.simulation_monitor import SteadyStateMonitor


def fixture_plan(tmp_path, stages, edges):
    topology = tmp_path / 'topology.txt'
    topology.write_text('7 3 2 6 25000000000 25000000000\n4 5 6\n'
                        '0 4 25000000000 2us 0\n1 4 25000000000 2us 0\n'
                        '2 5 25000000000 2us 0\n3 5 25000000000 2us 0\n'
                        '4 6 25000000000 2us 0\n5 6 25000000000 2us 0\n')
    load = tmp_path / 'load'
    for name, src, dst, size in stages:
        directory = load / name
        directory.mkdir(parents=True)
        if src is None:
            continue
        (directory / 'rdma_operate0.txt').write_text(
            'stat rdma operate:\nphase:0\n'
            f'Type rdma_send src_node {src} src_port 1000 dst_node {dst} '
            f'dst_port 1000 priority 0 msg_len {size}\n')
    tree = {'nodes': [{'name': name, 'type': 'TP'} for name, *_ in stages],
            'edges': [{'from': a, 'to': b} for a, b in edges]}
    return build_plan(tree, load, topology)


def write_lines(path, records):
    path.write_text(''.join(json.dumps(record)+'\n' for record in records), encoding='utf-8')


class FakeNetwork:
    """Deterministic FIFO service, used only to exercise orchestration invariants."""
    def __init__(self, corrupt_mixed=False, bias_mixed_operations=False, bias_packet_operations=False):
        self.jobs = []
        self.corrupt_mixed = corrupt_mixed
        self.bias_mixed_operations = bias_mixed_operations
        self.bias_packet_operations = bias_packet_operations
        self.lock = threading.Lock()

    def __call__(self, job):
        with self.lock:
            self.jobs.append(job)
        inputs = Path(job['input_dir']); output = Path(job['output_dir'])
        release = {int(line.split()[0]): int(line.split()[1])
                   for line in (inputs/'release_times.txt').read_text().splitlines()}
        predecessors = {index: [] for index in job['operations']}
        for line in (inputs/'dependence.txt').read_text().splitlines():
            if line.startswith('#') or not line: continue
            child, parent = map(int, line.split(':')); predecessors[child].append(parent)
        pending = set(predecessors); end = {}; operation_events = []; flow_events = []; busy = {}
        while pending:
            ready = [index for index in sorted(pending) if all(p in end for p in predecessors[index])]
            if not ready: raise RuntimeError('invalid fixture dependencies')
            for index in ready:
                operation = job['operations'][index]
                start = max([release[index], *[end[p] for p in predecessors[index]]])
                operation_events.append(dict(event='operation_start', operation_index=index, time_ns=start))
                phase_start = start
                for phase_index, phase in enumerate(operation['phases']):
                    finishes = []
                    for flow_index, flow in enumerate(phase):
                        duration = flow['msg_len'] + (2 if job['mixed'] and self.corrupt_mixed and flow['msg_len']%2==0 else 0)
                        if ((job['mixed'] and self.bias_mixed_operations)
                                or (not job['mixed'] and self.bias_packet_operations)):
                            duration += operation['local_index']
                        resource = (flow['src'], flow['dst'])
                        finish = max(phase_start, busy.get(resource, 0))+duration
                        busy[resource] = finish; finishes.append(finish)
                        flow_events.append(dict(event='flow_complete', operation_index=index,
                            phase_index=phase_index, flow_index=flow_index, src=flow['src'], dst=flow['dst'],
                            sport=flow['sport'], dport=flow['dport'], priority=flow['priority'],
                            size_bytes=flow['msg_len'], start_ns=phase_start,
                            finish_ns=finish, fct_ns=finish-phase_start))
                    phase_start = max(finishes, default=phase_start)
                end[index] = phase_start; pending.remove(index)
                operation_events.append(dict(event='operation_complete', operation_index=index, time_ns=phase_start))
        write_lines(output/'operation_events.jsonl', operation_events)
        write_lines(output/'flow_events.jsonl', flow_events)
        duration = max(end.values(), default=0)
        write_lines(output/'steady_events.jsonl', [
            dict(task_id=job['task_id'],event='enter',sim_time_ns=1,wall_clock_ts=1700000000),
            dict(task_id=job['task_id'],event='exit',sim_time_ns=max(1,duration),wall_clock_ts=1700000001)])
        (output/'flow_SwitchStats.txt').write_text('current input calibration\n')
        (output/'execution_metadata.json').write_text(json.dumps({
            'mixed_requested': job['mixed'], 'transition_count': int(job['mixed']),
            'mixed_policy': 'mixed' if job['mixed'] else 'packet',
            'simulation_wall_time_ns': 100 if job['mixed'] else 200}))


def test_three_instances_reuse_one_job_and_restore_dependency_time(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',2,3,10),('C',0,1,10)], [('A','C'),('B','C')])
    network = FakeNetwork(); monitor = SteadyStateMonitor()
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                validate=True, job_executor=network, monitor=monitor)
    assert result['success']
    assert result['summary']['logical_unit_count'] == 3
    assert result['summary']['representative_count'] == 1
    assert result['summary']['total_flows'] == 3
    assert result['summary']['total_bytes'] == 30
    assert result['summary']['makespan_ns'] == 20
    assert result['validation']['passed'] is True
    assert len(network.jobs) == 5  # 1 representative + 3 un-reused stages + 1 whole DAG
    schedule = {row['id']: row for row in result['schedule']}
    assert schedule['A']['start_ns'] == schedule['B']['start_ns'] == 0
    assert schedule['C']['start_ns'] == 10
    assert {flow['stage_id'] for flow in result['flows']} == {'A','B','C'}
    assert {flow['src'] for flow in result['flows']} == {0,2}
    events = result['steady_state_timeline']
    assert len([event for event in events if event['event']=='enter']) == 3
    assert all(event['wall_clock_ts'] is None for event in events if event['source']=='reused')
    assert all(event['actual_wall_clock_ts'] for event in events)
    assert len(monitor.snapshot()['history']) == 5
    assert not monitor.snapshot()['is_monitoring']
    manifest = json.loads((tmp_path/'run/manifest.json').read_text())
    assert manifest['success']
    assert len(manifest['jobs']) == 5
    assert all(job['exit_code'] == 0 for job in manifest['jobs'])


def test_actual_conflicts_merge_and_rerun_without_losing_stages(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',0,1,10)], [])
    network = FakeNetwork()
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                validate=True, job_executor=network)
    assert result['success']
    assert result['summary']['group_count'] == 1
    assert result['summary']['logical_unit_count'] == 2
    assert result['summary']['makespan_ns'] == 20
    assert result['refinement_rounds'][0]['conflicts']
    assert not result['refinement_rounds'][-1]['conflicts']
    assert result['validation']['passed']


def test_merged_group_external_releases_preserve_multiple_entries(tmp_path):
    # A must wait for P; B has no external predecessor. A+B share a resource.
    plan = fixture_plan(tmp_path, [('P',2,3,20),('A',0,1,10),('B',0,1,30)], [('P','A')])
    network = FakeNetwork()
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                validate=False, job_executor=network)
    assert result['summary']['group_count'] == 2
    merged = next(job for job in network.jobs if len(job['stage_ids'])==2)
    assert merged['releases']['A'] == 20
    assert merged['releases']['B'] == 0
    assert {row['id'] for row in result['schedule']} == {'P','A','B'}


def test_mixed_is_after_packet_validation_and_exposes_error(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    network = FakeNetwork(corrupt_mixed=True)
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                validate=True, mixed=True, job_executor=network)
    assert result['validation']['passed']
    assert result['mixed_comparison']['performed']
    assert not result['mixed_comparison']['passed']
    assert result['mixed_comparison']['max_fct_error_ns'] == 2
    assert result['mixed_comparison']['representatives_with_transitions'] == 1
    assert result['mixed_comparison']['runtime_speedup'] == 2
    assert network.jobs[-1]['mixed']
    calibration = Path(network.jobs[-1]['output_dir'])/'flow_SwitchStats.txt'
    assert calibration.read_text() == 'current input calibration\n'


def test_incomplete_telemetry_fails_instead_of_publishing_results(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    def missing(job):
        write_lines(Path(job['output_dir'])/'operation_events.jsonl', [])
    with pytest.raises(DagExecutionError, match='Incomplete operation telemetry'):
        run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False, job_executor=missing)
    assert (tmp_path/'run/error.json').exists()


def test_cancelled_run_never_spawns_jobs(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    network = FakeNetwork()
    state = SimpleNamespace(cancelled=True, lock=threading.RLock(), processes=set())
    with pytest.raises(DagCancelled):
        run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                           job_executor=network, state=state)
    assert network.jobs == []


def test_frozen_plan_does_not_read_later_input_changes(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    Path(plan['topology_file']).write_text('changed after planning')
    Path(plan['stages'][0]['operation_files'][0]).write_text('changed after planning')
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False, job_executor=FakeNetwork())
    assert result['summary']['makespan_ns'] == 10
    assert (tmp_path/'run/inputs/topology.txt').read_text().startswith('7 3 2 6')


def test_comparison_checks_flow_population_not_only_average(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False, job_executor=FakeNetwork())
    other = {**result, 'flows': []}
    comparison = compare_results(result, other)
    assert not comparison['passed'] and comparison['missing_flows'] == 1


def test_comparison_checks_noncritical_stage_windows(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',2,3,20)], [])
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False, job_executor=FakeNetwork())
    other = {**result, 'schedule': [dict(row) for row in result['schedule']]}
    other['schedule'][0]['start_ns'] += 1
    other['schedule'][0]['duration_ns'] -= 1
    comparison = compare_results(result, other)
    assert not comparison['passed']
    assert comparison['mismatched_stages'] == 1
    assert comparison['stage_examples'][0]['stage_id'] == 'A'


def test_mixed_new_resource_conflicts_refine_then_revalidate(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('P',2,3,11),('B',0,1,10)], [('P','B')])
    network = FakeNetwork(corrupt_mixed=True)
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                mixed=True, validate=True, job_executor=network)
    assert result['success'] and result['validation']['passed']
    assert result['summary']['group_count'] == 2
    assert any(row['mode']=='mixed' and row['conflicts'] for row in result['refinement_rounds'])
    assert not result['refinement_rounds'][-1]['conflicts']
    assert result['mixed_comparison']['performed']
    assert not result['mixed_comparison']['cross_group_conflicts']
    assert result['execution_plan']['counts']['group_count'] == 2
    assert list((tmp_path/'run').glob('mixed_conflict_round*.json'))


def test_empty_stage_is_a_zero_time_job_and_keeps_empty_join_barrier(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',2,3,20),('E',None,None,0),('C',0,1,10)],
                        [('A','E'),('B','E'),('E','C')])
    network = FakeNetwork()
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                validate=True, job_executor=network)
    assert result['success'] and result['validation']['passed']
    schedule = {row['id']: row for row in result['schedule']}
    assert schedule['E']['start_ns'] == schedule['E']['finish_ns'] == 20
    assert schedule['C']['start_ns'] == 20
    assert result['summary']['total_flows'] == 3
    whole = next(job for job in network.jobs if job['run_role']=='whole_dag_reference')
    dummy = next(op for op in whole['operations'].values() if op['stage_id']=='E')
    assert dummy['phases'] == [[]]


def test_comparison_rejects_wrong_flow_identity_even_when_count_matches(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    network = FakeNetwork()
    def wrong_identity(job):
        network(job)
        path = Path(job['output_dir'])/'flow_events.jsonl'
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[0]['dst'] = 3
        write_lines(path, records)
    with pytest.raises(DagExecutionError, match='flow population differs'):
        run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False, job_executor=wrong_identity)


def test_representative_worker_pool_actually_runs_two_concurrently(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',2,3,20),('C',0,1,30)], [('A','C')])
    network = FakeNetwork(); lock = threading.Lock(); two_running = threading.Event()
    active = 0; maximum = 0
    def concurrent(job):
        nonlocal active, maximum
        with lock:
            active += 1; maximum = max(maximum, active)
            if active == 2: two_running.set()
        try:
            assert two_running.wait(5), 'representatives did not execute concurrently'
            network(job)
        finally:
            with lock: active -= 1
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', build=False,
                                workers=2, job_executor=concurrent)
    assert result['success']
    assert maximum == 2
    assert len(network.jobs) == 3


def test_cancel_terminates_live_subprocess_and_clears_registry(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    state = SimpleNamespace(cancelled=False, lock=threading.RLock(), processes=set())
    runner = _Runner(plan, tmp_path, tmp_path/'run', workers=2, state=state,
                     monitor=None, job_timeout=10, job_executor=None, simulation_id='cancel')
    observed = []
    def cancel_when_started():
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            with state.lock:
                observed.extend(state.processes)
            if observed:
                state.cancelled = True
                return
            time.sleep(.01)
    watcher = threading.Thread(target=cancel_when_started)
    watcher.start()
    try:
        with pytest.raises(DagCancelled):
            runner.command([sys.executable, '-c', 'import time; time.sleep(60)'], tmp_path/'process')
    finally:
        watcher.join(timeout=5)
    assert observed and all(process.poll() is not None for process in observed)
    assert not state.processes


def permuted_operations_plan(tmp_path, shared_resource=False):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',0,1,10)], [('A','B')])
    base = plan['stages'][0]['operations'][0]
    flows = [dict(src=0,dst=1,sport=1000,dport=1000,priority=0,msg_len=10),
             dict(src=0 if shared_resource else 2,dst=1 if shared_resource else 3,
                  sport=1000,dport=1000,priority=0,msg_len=20)]
    for stage in plan['stages']:
        ordered = flows if stage['id']=='A' else flows[::-1]
        stage['operations'] = [dict(base, id=f"{stage['id']}:op{index}", index=index,
                                    predecessors=[], phases=[[deepcopy(flow)]])
                               for index, flow in enumerate(ordered)]
    return deduplicate_plan(plan)


def test_general_mapping_restores_operation_phase_and_flow_indices(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',2,3,10)], [('A','B')])
    source, target = plan['stages']
    original = source['operations'][0]
    flows = [dict(src=0,dst=1,sport=1000,dport=1000,priority=0,msg_len=size) for size in (10,11,12,13)]
    source['operations'] = [dict(original, id='A:op0', index=0, predecessors=[], phases=[flows[:2],flows[2:3]]),
                            dict(original, id='A:op1', index=1, predecessors=[], phases=[flows[3:]])]
    target['operations'] = [dict(original, id='B:op0', index=0, predecessors=[], phases=[[dict(flows[3],src=2,dst=3,sport=2000,dport=2000)]]),
                            dict(original, id='B:op1', index=1, predecessors=[], phases=[
                                [dict(flows[2],src=2,dst=3,sport=2000,dport=2000)],
                                [dict(flow,src=2,dst=3,sport=2000,dport=2000) for flow in flows[:2][::-1]]])]
    runner = _Runner(plan,tmp_path,tmp_path/'run',workers=2,monitor=None,state=None,
                     job_timeout=10,job_executor=FakeNetwork(),simulation_id='maps')
    job = runner._job(plan,plan['groups'][0],'source',{'A':0},False,'test')
    local = runner.execute(job)
    mapping = {'stage_map':{'A':'B'},'operation_map':{'A':{'0':1,'1':0}},
               'phase_map':{'A':{'0':{'0':1,'1':0},'1':{'0':0}}},
               'flow_map':{'A':{'0':{'0':{'0':1,'1':0},'1':{'0':0}},'1':{'0':{'0':0}}}},
               'node_map':{'0':2,'1':3},'port_map':{'1000':2000}}
    expanded = runner.expand(plan,plan['groups'][0],plan['groups'][1],local,100,mapping)
    for event in expanded['flows']:
        expected = target['operations'][event['operation_index']]['phases'][event['phase_index']][event['flow_index']]
        assert event['size_bytes'] == expected['msg_len']
        assert all(event[key] == expected[key] for key in ('src','dst','sport','dport','priority'))
        assert event['start_ns'] >= 100
        assert event['source_group_id'] == plan['groups'][0]['id']
    assert {event['operation_index'] for event in expanded['operations']} == {0,1}


def test_provisional_operation_permutation_requires_and_passes_independent_validation(tmp_path):
    plan = permuted_operations_plan(tmp_path)
    strict = run_dag_simulation(plan,tmp_path,tmp_path/'strict',build=False,validate=False,job_executor=FakeNetwork())
    assert strict['summary']['representative_count'] == 2
    result = run_dag_simulation(plan,tmp_path,tmp_path/'verified',build=False,validate=True,job_executor=FakeNetwork())
    assert result['success'] and result['validation']['passed']
    assert result['summary']['representative_count'] == 1
    report = result['deduplication_validation']['packet']
    assert report['performed'] and report['passed'] and not report['fallback']
    assert report['evidence_context']['mode'] == 'packet'
    assert report['evidence_context']['simulator_fingerprint']


def test_failed_packet_permutation_falls_back_and_retains_witness(tmp_path):
    plan = permuted_operations_plan(tmp_path)
    result = run_dag_simulation(plan,tmp_path,tmp_path/'run',build=False,validate=True,
                               job_executor=FakeNetwork(bias_packet_operations=True))
    assert result['success'] and result['validation']['passed']
    assert result['summary']['representative_count'] == 2
    report = result['deduplication_validation']['packet']
    assert report['fallback'] and report['passed']
    assert report['candidate_representative_count'] == 1 and report['final_representative_count'] == 2
    evidence = json.loads((tmp_path/'run'/report['candidate_evidence_file']).read_text())
    assert not evidence['comparisons']['dedup_vs_split_no_dedup']['passed']


@pytest.mark.parametrize('mismatch',['flow','steady'])
def test_packet_proof_does_not_replace_same_mode_mixed_witness(tmp_path,mismatch):
    plan = permuted_operations_plan(tmp_path)
    network = FakeNetwork(bias_mixed_operations=mismatch=='flow')
    def execute(job):
        network(job)
        if mismatch=='steady' and job['mixed'] and 'B' in job['stage_ids']:
            output = Path(job['output_dir'])
            events = [json.loads(line) for line in (output/'steady_events.jsonl').read_text().splitlines()]
            events[0]['sim_time_ns'] = 2
            write_lines(output/'steady_events.jsonl',events)
            metadata = json.loads((output/'execution_metadata.json').read_text())
            metadata['transition_count'] = 2
            (output/'execution_metadata.json').write_text(json.dumps(metadata))
    result = run_dag_simulation(plan,tmp_path,tmp_path/'run',mixed=True,validate=True,build=False,job_executor=execute)
    assert result['success'] and result['validation']['passed']
    assert result['deduplication_validation']['packet']['final_representative_count'] == 1
    report = result['deduplication_validation']['mixed']
    assert report['fallback'] and report['passed']
    assert report['candidate_representative_count'] == 1 and report['final_representative_count'] == 2
    assert result['summary']['representative_count'] == 2
    assert result['execution_plan']['counts']['representative_count'] == 2
    performance = result['mixed_comparison']['performance_reference']
    assert performance['valid'] and performance['matched_representative_inputs']
    assert performance['summary']['representative_count'] == 2
    assert performance['evidence_file'] == 'packet_performance_reference.json'
    packet_reference = json.loads((tmp_path/'run'/performance['evidence_file']).read_text())
    assert all(mapping['proof_mode'] == 'packet'
               for rep in packet_reference['plan']['representatives']
               for mapping in rep['mappings'].values())
    assert result['mixed_comparison']['packet_simulation_wall_time_ns'] == 400
    assert result['mixed_comparison']['runtime_speedup'] == 2
    evidence = json.loads((tmp_path/'run'/report['candidate_evidence_file']).read_text())
    assert not evidence['comparisons']['passed']
    if mismatch=='steady':
        assert evidence['comparisons']['mismatched_flows'] == 0
        assert evidence['comparisons']['mismatched_steady_groups'] == 1


@pytest.mark.parametrize('second_release',[20,30])
def test_multistage_reuse_matches_actual_external_release_profile(tmp_path,second_release):
    plan = fixture_plan(tmp_path,[('P',2,3,20),('Q',2,3,second_release),('A',0,1,10),
                                  ('B',2,3,10),('C',0,1,10),('D',2,3,10)],[('P','B'),('Q','D')])
    plan = refine_groups(plan,[('A','B'),('C','D')])
    network = FakeNetwork()
    runner = _Runner(plan,tmp_path,tmp_path/'run',workers=2,monitor=None,state=None,
                     job_timeout=10,job_executor=network,simulation_id='profiles')
    result = runner.run_plan(plan)
    merged_jobs = [job for job in network.jobs if len(job['stage_ids'])==2]
    assert len(merged_jobs) == (1 if second_release==20 else 2)
    if second_release==30:
        assert {max(job['releases'].values()) for job in merged_jobs} == {20,30}
    assert len(result['schedule']) == 6


def test_actual_native_route_interfaces_must_match_frozen_certificate(tmp_path):
    plan = fixture_plan(tmp_path,[('A',0,1,10)],[])
    route = {'forward':[0,4,1],'reverse':[1,4,0],
             'forward_hops':[{'node':0,'out_if':1,'next_node':4,'in_if':1},
                             {'node':4,'out_if':2,'next_node':1,'in_if':1}],
             'reverse_hops':[{'node':1,'out_if':1,'next_node':4,'in_if':2},
                             {'node':4,'out_if':1,'next_node':0,'in_if':1}]}
    plan['route_certificate'] = {'certified':True,'routes':{'0,1,1000,1000':route}}
    network = FakeNetwork()
    def changed_route(job):
        network(job)
        actual = deepcopy(job['route_certificate'])
        actual['routes']['0,1,1000,1000']['forward_hops'][0]['out_if'] = 9
        (Path(job['output_dir'])/'native_routes.json').write_text(json.dumps(actual))
    with pytest.raises(DagExecutionError,match='Actual native route differs'):
        run_dag_simulation(plan,tmp_path,tmp_path/'run',build=False,job_executor=changed_route)


def test_mixed_address_symmetry_needs_mode_specific_witness(tmp_path):
    plan = fixture_plan(tmp_path,[('A',0,1,10),('B',2,3,10)],[('A','B')])
    unverified = run_dag_simulation(plan,tmp_path,tmp_path/'strict',mixed=True,validate=False,
                                   build=False,job_executor=FakeNetwork())
    assert unverified['deduplication_validation']['packet']['final_representative_count'] == 1
    assert unverified['summary']['representative_count'] == 2
    verified = run_dag_simulation(plan,tmp_path,tmp_path/'verified',mixed=True,validate=True,
                                 build=False,job_executor=FakeNetwork())
    assert verified['success']
    assert verified['summary']['representative_count'] == 1
    report = verified['deduplication_validation']['mixed']
    assert report['performed'] and report['passed']
    assert report['mixed_verification_required']
    assert report['evidence_context']['mode'] == 'mixed'


def test_mixed_witness_preserves_equal_timestamp_event_order():
    reference = {'flows':[],'summary':{'makespan_ns':5},'schedule':[],
                 'group_execution':{'G':{'execution_metadata':{'transition_count':1}}},
                 'steady_state_timeline':[
                     {'group_id':'G','event':'enter','local_sim_time_ns':5},
                     {'group_id':'G','event':'exit','local_sim_time_ns':5}]}
    candidate = deepcopy(reference)
    candidate['steady_state_timeline'].reverse()
    comparison = compare_results(reference,candidate,compare_steady=True)
    assert not comparison['passed']
    assert comparison['mismatched_steady_groups'] == 1


def test_dedup_verification_keeps_provisional_reuse_without_a_whole_baseline(tmp_path):
    plan = permuted_operations_plan(tmp_path)
    original = deepcopy(plan)
    network = FakeNetwork()
    directory = tmp_path/'dedup-only'
    result = run_dag_simulation(plan, tmp_path, directory, validate=False,
                                verify_dedup=True, build=False, job_executor=network)
    assert result['success']
    assert result['validation'] == {'performed': False, 'passed': None}
    assert result['summary']['representative_count'] == 1
    evidence = result['deduplication_validation']['packet']
    assert evidence['performed'] and evidence['passed'] and not evidence['fallback']
    assert {job['run_role'] for job in network.jobs} == {'packet_representative', 'split_no_dedup'}
    assert len(network.jobs) == 3
    assert not (directory/'reference_whole_dag.json').exists()
    assert json.loads((directory/'dedup_packet_witness_comparison.json').read_text(encoding='utf-8'))['passed']
    assert plan == original


def test_dedup_only_packet_failure_falls_back_and_checks_strict_result(tmp_path):
    network = FakeNetwork(bias_packet_operations=True)
    result = run_dag_simulation(permuted_operations_plan(tmp_path), tmp_path, tmp_path/'run',
                                verify_dedup=True, validate=False, build=False, job_executor=network)
    assert result['success'] and not result['validation']['performed']
    assert result['summary']['representative_count'] == 2
    report = result['deduplication_validation']['packet']
    assert report['fallback'] and report['passed']
    assert report['candidate_representative_count'] == 1
    assert report['final_representative_count'] == 2
    assert not any(job['run_role'] == 'whole_dag_reference' for job in network.jobs)
    failure = json.loads((tmp_path/'run'/report['candidate_evidence_file']).read_text(encoding='utf-8'))
    assert not failure['comparisons']['dedup_vs_split_no_dedup']['passed']


def test_dedup_only_mixed_witness_remains_independent_without_whole_baseline(tmp_path):
    network = FakeNetwork(bias_mixed_operations=True)
    result = run_dag_simulation(permuted_operations_plan(tmp_path), tmp_path, tmp_path/'run',
                                mixed=True, verify_dedup=True, validate=False, build=False,
                                job_executor=network)
    assert result['success'] and not result['validation']['performed']
    assert result['deduplication_validation']['packet']['passed']
    report = result['deduplication_validation']['mixed']
    assert report['performed'] and report['fallback'] and report['passed']
    assert report['candidate_representative_count'] == 1
    assert report['final_representative_count'] == 2
    assert result['mixed_comparison']['performance_reference']['valid']
    assert not any(job['run_role'] == 'whole_dag_reference' for job in network.jobs)


def test_dedup_only_rejects_disagreement_that_survives_strict_fallback(tmp_path):
    network = FakeNetwork()
    def inconsistent_witness(job):
        network(job)
        if job['run_role'] == 'split_no_dedup' and job['stage_ids'] == ['B']:
            directory = Path(job['output_dir'])
            flows = [json.loads(line) for line in (directory/'flow_events.jsonl').read_text().splitlines()]
            changed = flows[0]
            changed['finish_ns'] += 1
            changed['fct_ns'] += 1
            write_lines(directory/'flow_events.jsonl', flows)
            events = [json.loads(line) for line in (directory/'operation_events.jsonl').read_text().splitlines()]
            for event in events:
                if event['event'] == 'operation_complete' and event['operation_index'] == changed['operation_index']:
                    event['time_ns'] += 1
            write_lines(directory/'operation_events.jsonl', events)
    with pytest.raises(DagExecutionError, match='even after strict fallback'):
        run_dag_simulation(permuted_operations_plan(tmp_path), tmp_path, tmp_path/'run',
                           verify_dedup=True, validate=False, build=False, job_executor=inconsistent_witness)
    assert not (tmp_path/'run/results.json').exists()
    assert not any(job['run_role'] == 'whole_dag_reference' for job in network.jobs)


def test_dedup_only_still_merges_simultaneous_competing_groups(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',0,1,10)], [])
    network = FakeNetwork()
    result = run_dag_simulation(plan, tmp_path, tmp_path/'run', verify_dedup=True,
                                validate=False, build=False, job_executor=network)
    assert result['success'] and not result['validation']['performed']
    assert result['summary']['group_count'] == 1
    assert result['summary']['makespan_ns'] == 20
    assert result['refinement_rounds'][0]['conflicts']
    assert not result['refinement_rounds'][-1]['conflicts']
    assert not any(job['run_role'] == 'whole_dag_reference' for job in network.jobs)


def test_analysis_baseline_executes_one_complete_frozen_packet_job(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10),('B',2,3,20),('E',None,None,0),('C',0,1,5)],
                        [('A','E'),('B','E'),('E','C')])
    original = deepcopy(plan)
    Path(plan['topology_file']).write_text('mutable topology changed after experiment')
    for stage in plan['stages']:
        for path in stage['operation_files']:
            Path(path).write_text('mutable traffic changed after experiment')
    network = FakeNetwork()
    directory = tmp_path/'baseline'
    state = SimpleNamespace(cancelled=False, lock=threading.RLock(), processes=set())
    monitor = SteadyStateMonitor()
    result = run_packet_baseline(plan, tmp_path, directory, job_executor=network,
                                 state=state, monitor=monitor, simulation_id='baseline-id')
    assert result['success'] and len(network.jobs) == 1
    job = network.jobs[0]
    assert job['run_role'] == 'analysis_whole_dag_baseline' and job['mixed'] is False
    assert set(job['stage_ids']) == {'A','B','E','C'}
    assert set(job['releases'].values()) == {0}
    assert result['summary']['group_count'] == result['summary']['representative_count'] == 1
    assert result['summary']['executed_jobs'] == 1
    assert result['summary']['total_flows'] == 3
    assert result['summary']['makespan_ns'] == 25
    assert result['summary']['simulation_wall_time_ns'] == 200
    assert result['baseline_policy'] == {
        'enable_cut':False, 'enable_mixed_granularity':False, 'deduplicate':False}
    assert not result['mixed_comparison']['performed']
    assert not result['validation']['performed']
    windows = {stage['id']:stage for stage in result['schedule']}
    assert windows['E']['start_ns'] == windows['E']['finish_ns'] == 20
    assert windows['C']['start_ns'] == 20
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['success'] and manifest['worker_count'] == 1
    assert manifest['purpose'] == 'analysis_whole_dag_baseline'
    assert manifest['simulator_fingerprint'] == 'test-executor'
    assert len(manifest['jobs']) == 1 and manifest['jobs'][0]['exit_code'] == 0
    assert json.loads((directory/'results.json').read_text(encoding='utf-8'))['execution_plan']['counts']['group_count'] == 1
    assert json.loads((directory/'plan.json').read_text(encoding='utf-8'))['deduplicate_enabled'] is False
    assert (directory/'inputs/topology.txt').read_text(encoding='utf-8').startswith('7 3 2 6')
    assert not state.processes
    assert monitor.snapshot()['simulation_id'] == 'baseline-id'
    assert not monitor.snapshot()['is_monitoring']
    assert plan == original


@pytest.mark.parametrize('when', ['before', 'during'])
def test_analysis_baseline_cancellation_does_not_publish_success(tmp_path, when):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    state = SimpleNamespace(cancelled=when=='before', lock=threading.RLock(), processes=set())
    network = FakeNetwork()
    def execute(job):
        network(job)
        state.cancelled = True
    with pytest.raises(DagCancelled):
        run_packet_baseline(plan, tmp_path, tmp_path/'baseline', state=state, job_executor=execute)
    assert len(network.jobs) == (0 if when=='before' else 1)
    assert not (tmp_path/'baseline/results.json').exists()
    manifest = json.loads((tmp_path/'baseline/manifest.json').read_text(encoding='utf-8'))
    assert manifest['success'] is False
    error = json.loads((tmp_path/'baseline/error.json').read_text(encoding='utf-8'))
    assert error['execution']['phase'] == 'cancelled'
    assert not state.processes


def test_analysis_baseline_rejects_incomplete_output(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    def incomplete(job):
        write_lines(Path(job['output_dir'])/'operation_events.jsonl', [])
    with pytest.raises(DagExecutionError, match='Incomplete operation telemetry'):
        run_packet_baseline(plan, tmp_path, tmp_path/'baseline', job_executor=incomplete)
    assert not (tmp_path/'baseline/results.json').exists()
    assert json.loads((tmp_path/'baseline/manifest.json').read_text(encoding='utf-8'))['success'] is False


def test_native_analysis_baseline_requires_frozen_route_evidence_before_launch(tmp_path, monkeypatch):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    monkeypatch.setattr(_Runner, 'fingerprint', lambda self: 'current-native-runtime')
    monkeypatch.setattr(_Runner, 'execute', lambda *args: pytest.fail('must not launch without route evidence'))
    with pytest.raises(DagExecutionError, match='frozen native route certificate'):
        run_packet_baseline(plan, tmp_path, tmp_path/'baseline')
    assert json.loads((tmp_path/'baseline/manifest.json').read_text(encoding='utf-8'))['success'] is False


def test_analysis_baseline_keeps_route_verification_and_rejects_changed_paths(tmp_path):
    plan = fixture_plan(tmp_path, [('A',0,1,10)], [])
    route = {'forward':[0,4,1], 'reverse':[1,4,0],
             'forward_hops':[{'node':0,'out_if':1,'next_node':4,'in_if':1},
                             {'node':4,'out_if':2,'next_node':1,'in_if':1}],
             'reverse_hops':[{'node':1,'out_if':1,'next_node':4,'in_if':2},
                             {'node':4,'out_if':1,'next_node':0,'in_if':1}]}
    plan['route_certificate'] = {'certified':True,'routes':{'0,1,1000,1000':route}}
    network = FakeNetwork()
    def changed(job):
        network(job)
        actual = deepcopy(job['route_certificate'])
        actual['routes']['0,1,1000,1000']['forward_hops'][0]['out_if'] = 9
        (Path(job['output_dir'])/'native_routes.json').write_text(json.dumps(actual))
    with pytest.raises(DagExecutionError, match='Actual native route differs'):
        run_packet_baseline(plan, tmp_path, tmp_path/'baseline', job_executor=changed)
    assert not (tmp_path/'baseline/results.json').exists()
