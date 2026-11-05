import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api import complete_api as api


@pytest.fixture
def dag_project(tmp_path, monkeypatch):
    root = tmp_path / 'Reverie'
    (root / 'api').mkdir(parents=True)
    (root / 'leaf-spine.txt').write_text(
        '7 3 2 6 25000000000 25000000000\n4 5 6\n'
        '0 4 25000000000 2us 0\n1 4 25000000000 2us 0\n'
        '2 5 25000000000 2us 0\n3 5 25000000000 2us 0\n'
        '4 6 25000000000 2us 0\n5 6 25000000000 2us 0\n')
    (root / 'config-workload.txt').write_text('CC_MODE 3\n')
    nodes = [{'name': 'Root', 'type': 'Root', 'layer': 0}]
    for name in 'ABCD':
        directory = root / 'rdma_result' / name
        directory.mkdir(parents=True)
        (directory / 'rdma_operate0.txt').write_text(
            'stat rdma operate:\nphase:1\n'
            'Type rdma_send src_node 0 src_port 1000 dst_node 1 dst_port 1000 priority 0 msg_len 32768\n')
        nodes.append({'name': name, 'type': 'TP', 'layer': 1, 'nodes_passed': ['FAKE']})
    edges = [('Root', 'A'), ('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')]
    tree = {'nodes': nodes, 'edges': [{'from_node': a, 'to_node': b} for a, b in edges]}
    monkeypatch.setattr(api, 'API_DIR', root / 'api')
    monkeypatch.setattr(api, 'REVERIE_ROOT', root)
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(api, 'simulation_status', api.SimulationStatus())
    monkeypatch.setattr(api, 'steady_state_monitor', api.SteadyStateMonitor())
    return root, tree


def cut(client, root, tree, **kwargs):
    return client.post('/tree-cut', json={'tree_data': tree,
        'rdma_root': str(root / 'rdma_result'), **kwargs})


def test_cut_exports_full_dag_and_automatic_representatives(dag_project):
    root, tree = dag_project
    with TestClient(api.app) as client:
        response = cut(client, root, tree, num_groups=4)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['tree_groups'] == 4
        assert result['execution_plan']['counts']['representative_count'] == 1
        stages = {stage['id']: stage for stage in result['execution_plan']['stages']}
        assert stages['D']['predecessors'] == ['B', 'C']
        saved = json.loads((root / 'api' / result['plan_file']).read_text(encoding='utf-8'))
        assert len(saved['edges']) == 4
        assert len(saved['stages']) == 4


def test_no_cut_is_one_whole_dag_job_and_no_dedup_is_one_job_per_stage(dag_project):
    root, tree = dag_project
    with TestClient(api.app) as client:
        whole = cut(client, root, tree, enable_cut=False).json()
        assert whole['tree_groups'] == 1
        assert whole['execution_plan']['counts']['representative_count'] == 1
        split = cut(client, root, tree, deduplicate=False).json()
        assert split['execution_plan']['counts']['representative_count'] == 4


def test_cut_exposes_unverified_symmetry_candidates_without_silently_using_them(dag_project):
    root, tree = dag_project
    first = ('Type rdma_send src_node 0 src_port 1000 dst_node 1 dst_port 1000 priority 0 msg_len 10\n')
    second = ('Type rdma_send src_node 2 src_port 2000 dst_node 3 dst_port 2000 priority 0 msg_len 20\n')
    for name, content in [('A', first + second), ('B', second + first)]:
        (root / 'rdma_result' / name / 'rdma_operate0.txt').write_text(
            'stat rdma operate:\nphase:0\n' + content, encoding='utf-8')
    tree['nodes'][1]['type'] = 'arbitrary_label'
    with TestClient(api.app) as client:
        response = cut(client, root, tree)
        assert response.status_code == 200, response.text
        result = response.json()
        projection = result['execution_plan']
        assert projection['counts']['representative_count'] == 3
        assert projection['deduplication']['candidate_representative_count'] == 2
        saved = json.loads((root / 'api' / result['plan_file']).read_text(encoding='utf-8'))
        assert saved['allow_provisional'] is False
        assert not projection['route_evidence']['certified']


def test_dag_start_uses_saved_plan_not_legacy_four_tasks(dag_project, monkeypatch):
    root, tree = dag_project
    calls = []
    monkeypatch.setattr(api, 'run_dag_execution', lambda *args: calls.append(args))
    monkeypatch.setattr(api, 'run_simulation', lambda *args, **kwargs: pytest.fail('legacy launcher called'))
    with TestClient(api.app) as client:
        plan = cut(client, root, tree).json()
        response = client.post('/run-simulation', json={
            'use_dag': True, 'plan_file': plan['plan_file'], 'task_num': 99,
            'workers': 3, 'validate': True, 'enable_mixed_granularity': False})
        assert response.status_code == 200, response.text
        assert calls[0][2:6] == (False, 3, False, True)
        assert len(calls[0][1]['stages']) == 4
        status = client.get('/simulation-status').json()
        assert status['execution']['logical_unit_count'] == 4
        assert status['execution']['representative_count'] == 1


def test_bad_plan_paths_and_cyclic_inputs_fail_clearly(dag_project):
    root, tree = dag_project
    with TestClient(api.app) as client:
        assert cut(client, root, tree, output_dir='../outside').status_code == 400
        tree['edges'].append({'from_node': 'D', 'to_node': 'A'})
        assert cut(client, root, tree).status_code == 400
        assert client.post('/run-simulation', json={'use_dag': True}).status_code == 400
        assert client.post('/run-simulation', json={'use_dag': True,
            'plan_file': '../../outside/plan.json'}).status_code == 400


def test_dag_analysis_requires_frozen_inputs_instead_of_running_legacy_baseline(dag_project, monkeypatch):
    api.simulation_status.current_task = 'finished'
    api.simulation_status.results['finished'] = {'mode': 'dag', 'success': True,
                                               'summary': {'makespan_ns': 123}}
    monkeypatch.setattr(api, 'run_simulation', lambda *args, **kwargs: pytest.fail('unexpected baseline'))
    with TestClient(api.app) as client:
        response = client.post('/analyze-results', json={'analysis_type': 'all'})
        assert response.status_code == 400, response.text
        assert '冻结输入' in response.json()['detail']
