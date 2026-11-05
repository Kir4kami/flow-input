"""Deferred full-DAG packet baselines are isolated, keyed, and single flight."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api import complete_api as api
from api.dag_plan import build_plan, refine_groups
from api.dag_runner import DagCancelled, run_dag_simulation

RUNTIME = 'a'*64
NEW_RUNTIME = 'b'*64
BINARY = 'c'*64


def write_jsonl(path, records):
    path.write_text(''.join(json.dumps(record)+'\n' for record in records), encoding='utf-8')


class PacketNetwork:
    """Only a test runner seam: write precise events, never invoke native ns-3."""
    def __call__(self, job):
        inputs, output = Path(job['input_dir']), Path(job['output_dir'])
        releases = {int(line.split()[0]): int(line.split()[1])
                    for line in (inputs/'release_times.txt').read_text().splitlines()}
        parents = {index: [] for index in job['operations']}
        for line in (inputs/'dependence.txt').read_text().splitlines():
            if line and not line.startswith('#'):
                child, parent = map(int, line.split(':'))
                parents[child].append(parent)
        pending, finish = set(parents), {}
        operation_events, flow_events = [], []
        while pending:
            ready = [index for index in sorted(pending) if all(parent in finish for parent in parents[index])]
            assert ready
            for index in ready:
                start = max([releases[index], *[finish[parent] for parent in parents[index]]])
                operation_events.append(dict(event='operation_start', operation_index=index, time_ns=start))
                phase_start = start
                for phase_index, phase in enumerate(job['operations'][index]['phases']):
                    operation_events.append(dict(event='phase_start', operation_index=index,
                                                 phase_index=phase_index, time_ns=phase_start))
                    phase_finish = phase_start
                    for flow_index, flow in enumerate(phase):
                        end = phase_start+flow['msg_len']
                        phase_finish = max(phase_finish, end)
                        flow_events.append(dict(event='flow_complete', operation_index=index,
                            phase_index=phase_index, flow_index=flow_index, src=flow['src'], dst=flow['dst'],
                            sport=flow['sport'], dport=flow['dport'], priority=flow['priority'],
                            size_bytes=flow['msg_len'], start_ns=phase_start, finish_ns=end, fct_ns=end-phase_start))
                    operation_events.append(dict(event='phase_complete', operation_index=index,
                                                 phase_index=phase_index, time_ns=phase_finish))
                    phase_start = phase_finish
                finish[index] = phase_start
                operation_events.append(dict(event='operation_complete', operation_index=index, time_ns=phase_start))
                pending.remove(index)
        write_jsonl(output/'operation_events.jsonl', operation_events)
        write_jsonl(output/'flow_events.jsonl', flow_events)
        write_jsonl(output/'steady_events.jsonl', [])
        (output/'execution_metadata.json').write_text(json.dumps({
            'mixed_requested': False, 'mixed_policy': 'packet', 'transition_count': 0,
            'completed_operations': len(finish), 'operation_count': len(finish),
            'finish_ns': max(finish.values(), default=0), 'simulation_event_count': len(flow_events)*8,
            'simulation_wall_time_ns': 1000, 'total_wall_time_ns': 2000}))


def packet_result(plan, project_root, run_dir, runtime=RUNTIME, state=None):
    result = run_dag_simulation(plan, project_root, run_dir, mixed=False, workers=1,
        validate=False, deduplicate=False, build=False, state=state, job_executor=PacketNetwork())
    result['mode'] = 'dag'
    result['native_runtime_sha256'] = runtime
    result['plan']['native_runtime_sha256'] = runtime
    for representative in result['representative_results'].values():
        representative.setdefault('evidence_context', {}).update(
            native_runtime_sha256=runtime, native_binary_sha256=BINARY)
        representative.setdefault('execution_metadata', {}).update(
            native_runtime_sha256=runtime, native_binary_sha256=BINARY)
    (Path(run_dir)/'results.json').write_text(json.dumps(result), encoding='utf-8')
    (Path(run_dir)/'plan.json').write_text(json.dumps(result['plan']), encoding='utf-8')
    return result


class BaselineRunner:
    def __init__(self, runtime=RUNTIME):
        self.runtime = runtime
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.failures = 0
        self.lock = threading.Lock()

    def __call__(self, plan, project_root, run_dir, *, state, build=False, **kwargs):
        assert build is False
        stage_ids = [stage['id'] for stage in plan['stages']]
        plan = refine_groups(plan, list(zip(stage_ids, stage_ids[1:])))
        assert len(plan['groups']) == 1
        assert set(plan['groups'][0]['stage_ids']) == set(stage_ids)
        with self.lock:
            self.calls.append({'plan': deepcopy(plan), 'run_dir': Path(run_dir), 'state': state})
        self.started.set()
        while not self.release.wait(.01):
            if state.cancelled:
                raise DagCancelled('test baseline cancelled')
        if state.cancelled:
            raise DagCancelled('test baseline cancelled')
        if self.failures:
            self.failures -= 1
            raise RuntimeError('injected baseline failure')
        return packet_result(plan, project_root, run_dir, self.runtime, state)


@pytest.fixture
def cases(tmp_path):
    def create(name='experiment', *, size=100, delay='2us', payload=1000,
               edges=None, priority=0, runtime=RUNTIME):
        project = tmp_path/name
        project.mkdir()
        load = project/'load'
        topology = project/'topology.txt'
        topology.write_text('7 3 2 6 25000000000 25000000000\n4 5 6\n'
            f'0 4 25000000000 {delay} 0\n1 4 25000000000 2us 0\n'
            '2 5 25000000000 2us 0\n3 5 25000000000 2us 0\n'
            '4 6 25000000000 2us 0\n5 6 25000000000 2us 0\n')
        config = project/'config.txt'
        config.write_text(f'PACKET_PAYLOAD_SIZE {payload}\nCC_MODE 0\n')
        for index, name in enumerate('ABCD'):
            directory = load/name
            directory.mkdir(parents=True)
            (directory/'rdma_operate0.txt').write_text('stat rdma operate:\nphase:0\n'
                f'Type rdma_send src_node {index%2*2} src_port 1000 dst_node {index%2*2+1} '
                f'dst_port 1000 priority {priority} msg_len {size+index}\n')
        tree = {'nodes': [{'name': 'Root'}, *[{'name': name, 'type': 'TP'} for name in 'ABCD']],
            'edges': [{'from':'Root','to':'A'}, *[{'from':a,'to':b} for a,b in
                (edges if edges is not None else [('A','B'),('A','C'),('B','D'),('C','D')])]]}
        plan = build_plan(tree, load, topology, config, deduplicate=False)
        run_dir = project/'dump/runs/experiment'
        experiment = packet_result(plan, project, run_dir, runtime)
        return experiment, run_dir, project
    return create


@pytest.fixture
def manager_factory(tmp_path):
    from api.dag_analysis import BaselineManager
    managers = []
    runners = []
    def create(project_root, *, runner=None, runtime_provider=None, cache_root=None):
        runner = runner or BaselineRunner()
        manager = BaselineManager(cache_root or tmp_path/'baselines', project_root,
            runner=runner, runtime_provider=runtime_provider or
                (lambda project: {'native_runtime_sha256': RUNTIME, 'native_binary_sha256': BINARY}))
        managers.append(manager)
        runners.append(runner)
        return manager, runner
    yield create
    for runner in runners:
        if hasattr(runner, 'release'):
            runner.release.set()
    for manager in managers:
        manager.shutdown()


def completed(future):
    value = future.result(timeout=10)
    assert value['baseline']['success'] is True
    assert value['baseline_status']['status'] == 'completed'
    return value


def wait_status(manager, experiment, run_dir, expected):
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        status = manager.status(experiment, run_dir)
        if status['status'] == expected:
            return status
        time.sleep(.01)
    pytest.fail(f'baseline status never reached {expected}: {status}')


def test_deferred_baseline_is_single_flight_and_retains_dag_dependencies(cases, manager_factory):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    assert manager.status(experiment, run_dir)['status'] == 'not_started'
    runner.release.clear()
    first = manager.get_or_run(experiment, run_dir)
    assert runner.started.wait(5)
    second = manager.get_or_run(experiment, run_dir)
    assert first is second
    assert manager.status(experiment, run_dir)['is_running'] is True
    assert len(runner.calls) == 1
    assert runner.calls[0]['plan']['edges'] == experiment['plan']['edges']
    runner.release.set()
    value = completed(first)
    assert value['baseline_status']['reused'] is False
    assert len(value['baseline']['flows']) == 4
    assert value['baseline']['summary']['mixed_granularity'] is False
    assert value['baseline']['summary']['group_count'] == 1
    assert manager.status(experiment, run_dir)['has_baseline'] is True


def test_second_analysis_reuses_completed_baseline(cases, manager_factory):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    first = completed(manager.get_or_run(experiment, run_dir))
    second = completed(manager.get_or_run(experiment, run_dir))
    assert len(runner.calls) == 1
    assert second['baseline_status']['reused'] is True
    assert first['baseline_status']['cache_key'] == second['baseline_status']['cache_key']


def test_partition_and_source_paths_do_not_invalidate_matching_whole_baseline(cases, manager_factory):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    first = completed(manager.get_or_run(experiment, run_dir))
    regrouped = deepcopy(experiment)
    regrouped['plan'] = refine_groups(experiment['plan'], [('A','B'),('C','D')])
    regrouped['plan']['runtime_boundary_releases'] = {'B': 777, 'C': 888}
    regrouped['plan']['rdma_root'] = '/different/source/path'
    regrouped['plan']['topology_file'] = '/different/topology.txt'
    regrouped['plan']['config_file'] = '/different/config.txt'
    for stage in regrouped['plan']['stages']:
        stage['operation_files'] = ['/different/operation.txt']
        for operation in stage['operations']:
            operation['source_file'] = '/different/operation.txt'
    regrouped_dir = project/'dump/runs/regrouped'
    regrouped_dir.mkdir()
    (regrouped_dir/'input_plan.json').write_text(json.dumps(regrouped['plan']))
    second = completed(manager.get_or_run(regrouped, regrouped_dir))
    assert len(runner.calls) == 1
    assert first['baseline_status']['cache_key'] == second['baseline_status']['cache_key']


@pytest.mark.parametrize('difference', ['flow_size','topology','protocol','dependency','priority'])
def test_semantic_input_change_requires_a_new_baseline(cases, manager_factory, difference):
    experiment, run_dir, project = cases()
    options = {'flow_size': {'size':101}, 'topology': {'delay':'3us'},
        'protocol': {'payload':1400}, 'dependency': {'edges':[('A','B'),('B','C'),('C','D')]},
        'priority': {'priority':1}}
    changed, changed_dir, _ = cases('changed', **options[difference])
    manager, runner = manager_factory(project)
    first = completed(manager.get_or_run(experiment, run_dir))
    assert manager.status(changed, changed_dir)['has_baseline'] is False
    second = completed(manager.get_or_run(changed, changed_dir))
    assert len(runner.calls) == 2
    assert first['baseline_status']['cache_key'] != second['baseline_status']['cache_key']


def test_runtime_change_rejects_old_experiment_and_does_not_reuse_old_cache(cases, manager_factory):
    experiment, run_dir, project = cases()
    current = {'value':RUNTIME}
    runner = BaselineRunner()
    manager, _ = manager_factory(project, runner=runner,
        runtime_provider=lambda root:{'native_runtime_sha256':current['value']})
    first = completed(manager.get_or_run(experiment, run_dir))
    current['value'] = NEW_RUNTIME
    with pytest.raises(ValueError):
        manager.get_or_run(experiment, run_dir)
    assert len(runner.calls) == 1
    fresh, fresh_dir, _ = cases('fresh-runtime', runtime=NEW_RUNTIME)
    runner.runtime = NEW_RUNTIME
    second = completed(manager.get_or_run(fresh, fresh_dir))
    assert second['baseline_status']['cache_key'] != first['baseline_status']['cache_key']
    assert len(runner.calls) == 2


def test_partial_runtime_evidence_cannot_certify_a_multi_representative_experiment(
        cases, manager_factory):
    experiment, run_dir, project = cases()
    assert len(experiment['representative_results']) > 1
    # A current plan certificate and the other jobs' hashes must not hide one
    # actual representative whose execution-runtime evidence is missing.
    experiment['plan']['route_certificate'] = {'native_runtime_sha256':RUNTIME}
    first = next(iter(experiment['representative_results'].values()))
    first['evidence_context'].pop('native_runtime_sha256')
    manager, runner = manager_factory(project)
    with pytest.raises(ValueError):
        manager.get_or_run(experiment, run_dir)
    assert not runner.calls


def test_failed_attempt_is_not_cached_and_retry_uses_new_directory(cases, manager_factory):
    experiment, run_dir, project = cases()
    runner = BaselineRunner()
    runner.failures = 1
    manager, _ = manager_factory(project, runner=runner)
    with pytest.raises(RuntimeError, match='injected baseline failure'):
        manager.get_or_run(experiment, run_dir).result(timeout=10)
    status = wait_status(manager, experiment, run_dir, 'failed')
    assert not status['has_baseline'] and not status['is_running']
    assert 'injected baseline failure' in status['error']
    value = completed(manager.get_or_run(experiment, run_dir))
    assert value['baseline_status']['reused'] is False
    assert len(runner.calls) == 2
    assert runner.calls[0]['run_dir'] != runner.calls[1]['run_dir']


def test_cancelled_baseline_can_be_retried_without_caching_partial_result(cases, manager_factory):
    experiment, run_dir, project = cases()
    runner = BaselineRunner()
    runner.release.clear()
    manager, _ = manager_factory(project, runner=runner)
    future = manager.get_or_run(experiment, run_dir)
    assert runner.started.wait(5)
    assert manager.cancel(experiment, run_dir) is True
    with pytest.raises((DagCancelled, CancelledError)):
        future.result(timeout=10)
    status = wait_status(manager, experiment, run_dir, 'cancelled')
    assert not status['has_baseline'] and not status['is_running']
    runner.release.set()
    completed(manager.get_or_run(experiment, run_dir))
    assert len(runner.calls) == 2


def test_successful_cache_survives_manager_restart(cases, manager_factory):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    first = completed(manager.get_or_run(experiment, run_dir))
    manager.shutdown()
    restarted, fresh_runner = manager_factory(project)
    second = completed(restarted.get_or_run(experiment, run_dir))
    assert second['baseline_status']['reused'] is True
    assert first['baseline_status']['cache_key'] == second['baseline_status']['cache_key']
    assert len(runner.calls) == 1 and not fresh_runner.calls


def test_incomplete_or_tampered_cache_is_not_reused(cases, manager_factory, tmp_path):
    experiment, run_dir, project = cases()
    manager, _ = manager_factory(project)
    value = completed(manager.get_or_run(experiment, run_dir))
    manager.shutdown()
    cache = tmp_path/'baselines'/value['baseline_status']['cache_key']/'result.json'
    envelope = json.loads(cache.read_text())
    envelope['baseline']['flows'][0]['fct_ns'] += 1
    cache.write_text(json.dumps(envelope))
    restarted, runner = manager_factory(project)
    assert restarted.status(experiment, run_dir)['has_baseline'] is False
    value = completed(restarted.get_or_run(experiment, run_dir))
    assert value['baseline_status']['reused'] is False
    assert len(runner.calls) == 1


def test_baseline_does_not_modify_experiment_snapshot_or_result(cases, manager_factory):
    experiment, run_dir, project = cases()
    before = deepcopy(experiment)
    files = {path:path.read_bytes() for path in run_dir.rglob('*') if path.is_file()}
    manager, _ = manager_factory(project)
    completed(manager.get_or_run(experiment, run_dir))
    assert experiment == before
    assert all(path.read_bytes() == content for path,content in files.items())


def test_existing_complete_whole_packet_reference_is_adopted_without_rerun(cases, manager_factory):
    experiment, run_dir, project = cases()
    stages = [stage['id'] for stage in experiment['plan']['stages']]
    whole_plan = refine_groups(experiment['plan'], list(zip(stages, stages[1:])))
    reference = packet_result(whole_plan, project, project/'existing-baseline')
    (run_dir/'reference_whole_dag.json').write_text(json.dumps(reference))
    manager, runner = manager_factory(project)
    value = completed(manager.get_or_run(experiment, run_dir))
    assert value['baseline_status']['reused'] is True
    assert not runner.calls


def legacy_whole_reference(experiment, project, output):
    stages = [stage['id'] for stage in experiment['plan']['stages']]
    whole_plan = refine_groups(experiment['plan'], list(zip(stages, stages[1:])))
    result = packet_result(whole_plan, project, output)
    # This is the actual _Runner.run_plan return shape written by older
    # validation jobs, before run_dag_simulation adds wrapper-level success.
    reference = {key:result[key] for key in ['summary','schedule','flows','operations',
        'steady_state_timeline','representative_results','group_execution','plan']}
    assert 'success' not in reference
    return reference


def test_complete_legacy_whole_reference_without_success_imports_with_verified_routes(
        cases, manager_factory):
    experiment, run_dir, project = cases()
    reference = legacy_whole_reference(experiment, project, project/'legacy-reference')
    for local in reference['representative_results'].values():
        local['route_verification'] = {'performed':True,'passed':True}
    reference_file = run_dir/'reference_whole_dag.json'
    reference_file.write_text(json.dumps(reference))
    manager, runner = manager_factory(project)
    value = completed(manager.get_or_run(experiment, run_dir))
    assert value['baseline_status']['reused'] is True
    assert value['baseline_status']['source'] == 'existing_whole_reference'
    assert value['baseline']['success'] is True
    assert value['baseline']['flows'] == reference['flows']
    assert 'success' not in json.loads(reference_file.read_text())
    assert not runner.calls


def test_legacy_reference_without_success_cannot_import_missing_or_failed_route_evidence(
        cases, manager_factory):
    for name, route_evidence in [('missing-route',None),('failed-route',{'performed':True,'passed':False})]:
        experiment, run_dir, project = cases(name)
        reference = legacy_whole_reference(experiment, project, project/'unverified-legacy-reference')
        for local in reference['representative_results'].values():
            if route_evidence is None:
                local.pop('route_verification',None)
            else:
                local['route_verification'] = route_evidence
        (run_dir/'reference_whole_dag.json').write_text(json.dumps(reference))
        # Each bad reference has an independent cache so one new successful
        # fake baseline cannot make the other case pass through cache reuse.
        manager, runner = manager_factory(project,cache_root=project/'baseline-cache')
        value = completed(manager.get_or_run(experiment, run_dir))
        assert value['baseline_status']['reused'] is False
        assert value['baseline_status']['source'] == 'new_baseline'
        assert len(runner.calls) == 1


def test_whole_packet_experiment_itself_is_already_a_baseline_and_never_reruns(
        cases, manager_factory):
    experiment, _, project = cases()
    stages = [stage['id'] for stage in experiment['plan']['stages']]
    whole_plan = refine_groups(experiment['plan'], list(zip(stages, stages[1:])))
    whole_dir = project/'dump/runs/whole-packet-experiment'
    whole = packet_result(whole_plan, project, whole_dir)
    assert whole['summary']['group_count'] == whole['summary']['representative_count'] == 1
    assert whole['summary']['mixed_granularity'] is False
    assert whole['summary']['executed_jobs'] == 1
    manager, runner = manager_factory(project)
    value = completed(manager.get_or_run(whole, whole_dir))
    assert value['baseline_status']['reused'] is True
    assert value['baseline_status']['source'] == 'existing_whole_experiment'
    assert value['baseline']['flows'] == whole['flows']
    assert not runner.calls


def test_existing_whole_reference_with_different_original_release_is_not_adopted(
        cases, manager_factory):
    experiment, run_dir, project = cases()
    stages = [stage['id'] for stage in experiment['plan']['stages']]
    whole_plan = refine_groups(experiment['plan'], list(zip(stages, stages[1:])))
    reference = packet_result(whole_plan, project, project/'wrong-release-reference')
    # Flow identity, dependencies, topology and native runtime all still match.
    # The original external release is a semantic difference, not a derived
    # runtime_boundary_releases field that may be discarded for cache identity.
    reference['plan']['boundary_releases'] = {
        **reference['plan'].get('boundary_releases', {}), 'A':12345}
    (run_dir/'reference_whole_dag.json').write_text(json.dumps(reference))
    manager, runner = manager_factory(project)
    value = completed(manager.get_or_run(experiment, run_dir))
    assert value['baseline_status']['reused'] is False
    assert len(runner.calls) == 1


def test_fct_chart_aligns_flow_identity_and_balanced_errors_are_not_hidden_by_equal_means(
        cases, manager_factory):
    from api.dag_analysis import analyze_dag_results
    experiment, run_dir, project = cases()
    manager, _ = manager_factory(project)
    payload = completed(manager.get_or_run(experiment, run_dir))
    baseline = payload['baseline']
    reordered = deepcopy(experiment)
    reordered['flows'].reverse()
    aligned = analyze_dag_results(reordered, baseline, payload['baseline_status'])
    assert aligned['fct_analysis']['sampled_fct_values'] == \
        aligned['baseline_analysis']['fct_analysis']['sampled_fct_values']
    assert aligned['comparison']['max_abs_fct_error_ns'] == 0
    by_stage = {flow['stage_id']:flow for flow in reordered['flows']}
    for name, delta in [('A',10),('B',-10)]:
        by_stage[name]['fct_ns'] += delta
        by_stage[name]['finish_ns'] += delta
    changed = analyze_dag_results(reordered, baseline, payload['baseline_status'])
    # An average-only check would falsely label these equal averages perfect.
    assert changed['fct_analysis']['average_fct_us'] == pytest.approx(
        changed['baseline_analysis']['fct_analysis']['average_fct_us'])
    comparison = changed['comparison']
    assert comparison['max_abs_fct_error_ns'] == 10
    assert comparison['mean_abs_relative_fct_error_percent'] == pytest.approx((10/100+10/101)/4*100)
    assert comparison['fct_fidelity'] < 1
    assert {row['stage_id']:row['fct_delta_ns'] for row in comparison['per_flow']} == {
        'A':10,'B':-10,'C':0,'D':0}
    assert changed['fct_analysis']['sampled_fct_values'] == pytest.approx([.110,.091,.102,.103])


@pytest.mark.parametrize('corruption',['mixed','partial','runtime'])
def test_invalid_existing_reference_does_not_satisfy_baseline(cases, manager_factory, corruption):
    experiment, run_dir, project = cases()
    stages = [stage['id'] for stage in experiment['plan']['stages']]
    reference = packet_result(refine_groups(experiment['plan'], list(zip(stages, stages[1:]))),
                              project, project/'bad-reference')
    if corruption == 'mixed':
        next(iter(reference['representative_results'].values()))['execution_metadata']['mixed_requested'] = True
    elif corruption == 'partial':
        reference['flows'].pop()
    else:
        next(iter(reference['representative_results'].values()))['evidence_context']['native_runtime_sha256'] = NEW_RUNTIME
    (run_dir/'reference_whole_dag.json').write_text(json.dumps(reference))
    manager, runner = manager_factory(project)
    value = completed(manager.get_or_run(experiment, run_dir))
    assert value['baseline_status']['reused'] is False
    assert len(runner.calls) == 1


def bind_api_experiment(monkeypatch, experiment, run_dir, project, manager):
    (project/'api').mkdir(exist_ok=True)
    state = api.SimulationStatus()
    state.current_task = run_dir.name
    state.run_dir = run_dir
    state.results = {run_dir.name: experiment}
    state.execution = {'phase':'completed','sentinel':'experiment execution'}
    monkeypatch.setattr(api, 'simulation_status', state)
    monkeypatch.setattr(api, 'REVERIE_ROOT', project)
    monkeypatch.setattr(api, 'API_DIR', project/'api')
    monkeypatch.setattr(api, 'PROJECT_ROOT', project)
    monkeypatch.setattr(api, '_dag_baseline_manager', lambda:manager)
    return state


def test_analyze_endpoint_runs_baseline_once_then_automatically_returns_comparison(
        cases, manager_factory, monkeypatch):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    state = bind_api_experiment(monkeypatch, experiment, run_dir, project, manager)
    before = deepcopy(state.results)
    saved_result = (run_dir/'results.json').read_bytes()
    with TestClient(api.app) as client:
        status = client.get('/baseline-status', params={'simulation_id':'experiment'})
        assert status.status_code == 200
        assert status.json()['status'] == 'not_started'
        first = client.post('/analyze-results', json={'simulation_id':'experiment','analysis_type':'all'})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body['success'] is True
        assert body['results']['baseline_status']['status'] == 'completed'
        assert body['results']['baseline_status']['reused'] is False
        assert body['results']['fct_analysis']['total_flows'] == 4
        assert body['results']['baseline_analysis']['fct_analysis']['total_flows'] == 4
        assert body['results']['comparison']['flow_population_match'] is True
        assert body['results']['comparison']['max_abs_fct_error_ns'] == 0
        assert body['results']['dag_result']['summary'] == experiment['summary']
        second = client.post('/analyze-results', json={'simulation_id':'experiment','analysis_type':'fct'})
        assert second.status_code == 200, second.text
        assert second.json()['results']['baseline_status']['reused'] is True
        assert second.json()['analysis_type'] == 'fct'
        assert client.get('/baseline-status', params={'simulation_id':'experiment'}).json()['has_baseline'] is True
    assert len(runner.calls) == 1
    assert state.results == before and state.current_task == 'experiment'
    assert state.execution == {'phase':'completed','sentinel':'experiment execution'}
    assert (run_dir/'results.json').read_bytes() == saved_result
    assert (run_dir/'analysis.json').is_file()


def test_baseline_status_remains_responsive_and_cancel_does_not_stop_main_experiment(
        cases, manager_factory, monkeypatch):
    experiment, run_dir, project = cases()
    runner = BaselineRunner()
    runner.release.clear()
    manager, _ = manager_factory(project, runner=runner)
    state = bind_api_experiment(monkeypatch, experiment, run_dir, project, manager)
    before = deepcopy(state.results)
    with TestClient(api.app) as client, ThreadPoolExecutor(max_workers=1) as requests:
        pending = requests.submit(client.post, '/analyze-results', json={'simulation_id':'experiment'})
        assert runner.started.wait(5)
        started = time.monotonic()
        running = client.get('/baseline-status', params={'simulation_id':'experiment'})
        assert time.monotonic()-started < 2, 'Status must not wait for the native baseline'
        assert running.status_code == 200 and running.json()['status'] == 'running'
        cancelled = client.post('/cancel-baseline', json={'simulation_id':'experiment'})
        assert cancelled.status_code == 200 and cancelled.json()['cancelled'] is True
        result = pending.result(timeout=10)
        assert result.status_code == 409
        stopped = client.get('/baseline-status', params={'simulation_id':'experiment'}).json()
        assert stopped['status'] == 'cancelled' and stopped['has_baseline'] is False
    assert state.results == before and state.current_task == 'experiment'
    assert state.cancelled is False and state.is_running is False
    assert not (run_dir/'analysis.json').exists()


def test_analysis_failure_reports_error_without_publishing_success_or_overwriting_experiment(
        cases, manager_factory, monkeypatch):
    experiment, run_dir, project = cases()
    runner = BaselineRunner()
    runner.failures = 1
    manager, _ = manager_factory(project, runner=runner)
    state = bind_api_experiment(monkeypatch, experiment, run_dir, project, manager)
    before = deepcopy(state.results)
    with TestClient(api.app) as client:
        response = client.post('/analyze-results', json={'simulation_id':'experiment'})
        assert response.status_code == 500
        assert 'injected baseline failure' in response.text
        status = client.get('/baseline-status', params={'simulation_id':'experiment'}).json()
        assert status['status'] == 'failed' and not status['has_baseline']
        assert not (run_dir/'analysis.json').exists()
        retry = client.post('/analyze-results', json={'simulation_id':'experiment'})
        assert retry.status_code == 200, retry.text
    assert state.results == before
    assert len(runner.calls) == 2


def test_saved_experiment_and_matching_baseline_survive_api_memory_reset(
        cases, manager_factory, monkeypatch):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    completed(manager.get_or_run(experiment, run_dir))
    state = bind_api_experiment(monkeypatch, experiment, run_dir, project, manager)
    state.results = {}
    with TestClient(api.app) as client:
        response = client.post('/analyze-results', json={'simulation_id':'experiment'})
    assert response.status_code == 200, response.text
    assert response.json()['results']['baseline_status']['reused'] is True
    assert len(runner.calls) == 1


def test_complete_saved_dag_without_old_mode_marker_still_reuses_matching_baseline(
        cases, manager_factory, monkeypatch):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    state = bind_api_experiment(monkeypatch, experiment, run_dir, project, manager)
    with TestClient(api.app) as client:
        initial = client.post('/analyze-results', json={'simulation_id':'experiment'})
        assert initial.status_code == 200, initial.text
        assert initial.json()['results']['baseline_status']['reused'] is False
        # Older native DAG runs saved all frozen input/runtime/result evidence,
        # but API code added mode='dag' to memory only. Preserve that complete
        # real schema and remove only the historically missing marker.
        saved_file = run_dir/'results.json'
        saved = json.loads(saved_file.read_text())
        assert saved['plan'] and saved['execution_plan'] and saved['representative_results']
        saved.pop('mode')
        saved_file.write_text(json.dumps(saved))
        state.results = {}
        restored = client.post('/analyze-results', json={'simulation_id':'experiment'})
        assert restored.status_code == 200, restored.text
        assert restored.json()['results']['baseline_status']['reused'] is True
        assert restored.json()['results']['comparison']['flow_population_match'] is True
        assert restored.json()['results']['comparison']['max_abs_fct_error_ns'] == 0
    assert len(runner.calls) == 1


def test_analysis_requires_a_finished_known_experiment(cases, manager_factory, monkeypatch):
    experiment, run_dir, project = cases()
    manager, runner = manager_factory(project)
    state = bind_api_experiment(monkeypatch, experiment, run_dir, project, manager)
    with TestClient(api.app) as client:
        assert client.post('/analyze-results', json={'simulation_id':'missing'}).status_code == 404
        assert client.post('/analyze-results', json={'simulation_id':'../../outside'}).status_code == 404
        state.is_running = True
        assert client.post('/analyze-results', json={'simulation_id':'experiment'}).status_code == 409
    assert not runner.calls
