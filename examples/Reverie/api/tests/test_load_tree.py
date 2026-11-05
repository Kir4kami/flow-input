"""Exercise the real traffic generator instead of substituting simulator input."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'examples/Reverie'))
from api import complete_api as api


@pytest.fixture
def generator_project(tmp_path, monkeypatch):
    root = tmp_path / 'Reverie'
    generator = root / 'Generator/Generator/TrafficGenerator'
    generator.mkdir(parents=True)
    (root / 'api').mkdir()
    (root / 'sim.sh').write_text('# test execution directory\n')
    original = REPO / 'examples/Reverie/Generator/Generator/TrafficGenerator'
    for name in ['trafficGen.py', 'merge_rdma.sh', 'merge_rdma.py',
                 'merge_dependency.py', 'qwen.txt', 'deepseek.txt']:
        shutil.copyfile(original / name, generator / name)
    monkeypatch.setattr(api, 'REVERIE_ROOT', root)
    monkeypatch.setattr(api, 'API_DIR', root / 'api')
    monkeypatch.setattr(api, 'is_ecmp_module_ready', lambda: False)
    return root, generator


@pytest.mark.parametrize('model', ['qwen', 'deepseek'])
@pytest.mark.skipif(os.name == 'nt', reason='Run the real Bash merge pipeline in Linux')
def test_load_then_tree_and_visualization(generator_project, model):
    root, generator = generator_project
    with TestClient(api.app) as client:
        payload = dict(host_num=64, msg_len='32*(1024)', dp=8, device=0,
                       forward=1, model_name=model, task_num=1)
        response = client.post('/generate-load', json=payload)
        assert response.status_code == 200, response.text
        load = response.json()
        assert Path(load['rdma_root']) == generator / 'rdma_result'
        tree_file = Path(load['rdma_root']) / 'communication_tree_iter0.json'
        assert tree_file.is_file()
        for node in json.loads(tree_file.read_text())['nodes'][1:]:
            assert (tree_file.parent / node['name']).is_dir()
        request = dict(load_source='generated', rdma_root=load['rdma_root'])
        response = client.post('/generate-communication-tree', json=request)
        assert response.status_code == 200, response.text
        tree = response.json()
        assert tree['nodes_count'] > 1 and tree['edges_count'] > 0
        assert tree['rdma_root'] == load['rdma_root']
        response = client.post('/visualize-full-tree', json=request)
        assert response.status_code == 200, response.text
        assert (root / 'task1/rdma_operate0.txt').is_file()


def test_explicit_load_never_reads_a_tree_from_another_directory(generator_project):
    root, generator = generator_project
    old = root / 'TrafficGenerator/rdma_result'
    old.mkdir(parents=True)
    (old / 'communication_tree_iter0.json').write_text('{"nodes":[],"edges":[]}')
    current = generator / 'rdma_result'
    current.mkdir()
    with TestClient(api.app) as client:
        response = client.post('/generate-communication-tree', json={
            'load_source': 'generated', 'rdma_root': str(current)})
        assert response.status_code == 404
        assert client.post('/generate-communication-tree', json={
            'rdma_root': str(root.parent)}).status_code == 400


def test_generator_failure_has_nonzero_exit_code(generator_project):
    _, generator = generator_project
    invalid = generator / 'bad.txt'
    invalid.write_text('invalid input\n')
    result = subprocess.run([sys.executable, str(generator / 'trafficGen.py'),
                             '--input_file', str(invalid)], cwd=generator,
                            capture_output=True, text=True)
    assert result.returncode != 0
