"""The visualization must use the current DAG plan, never cached tree cuts."""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api import complete_api as api


def projection(final=False):
    """A diamond DAG, including a join that a tree layout must not duplicate."""
    if final:
        members = {'group1': ['A', 'B', 'C'], 'group2': ['D']}
        group_predecessors = {'group1': [], 'group2': ['group1']}
        group_to_rep = {'group1': 'rep1', 'group2': 'rep2'}
        representatives = [
            {'id': 'rep1', 'group_id': 'group1', 'member_group_ids': ['group1']},
            {'id': 'rep2', 'group_id': 'group2', 'member_group_ids': ['group2']},
        ]
    else:
        members = {'group1': ['A'], 'group2': ['B'], 'group3': ['C', 'D']}
        group_predecessors = {'group1': [], 'group2': ['group1'],
                              'group3': ['group1', 'group2']}
        group_to_rep = {'group1': 'rep1', 'group2': 'rep1', 'group3': 'rep2'}
        representatives = [
            {'id': 'rep1', 'group_id': 'group1', 'member_group_ids': ['group1', 'group2']},
            {'id': 'rep2', 'group_id': 'group3', 'member_group_ids': ['group3']},
        ]
    stage_to_group = {stage: group for group, stages in members.items() for stage in stages}
    parents = {'A': [], 'B': ['A'], 'C': ['A'], 'D': ['B', 'C']}
    return {
        'counts': {'logical_unit_count': 4, 'group_count': len(members),
                   'representative_count': 2, 'reused_unit_count': 0 if final else 1,
                   'reused_group_count': 0 if final else 1},
        'stages': [{'id': name, 'type': 'TP', 'predecessors': parents[name],
                    'group_id': stage_to_group[name],
                    'representative_id': group_to_rep[stage_to_group[name]],
                    'operation_count': 1} for name in 'ABCD'],
        'edges': [['A', 'B'], ['A', 'C'], ['B', 'D'], ['C', 'D']],
        'groups': [{'id': group, 'stage_ids': stages,
                    'predecessors': group_predecessors[group]} for group, stages in members.items()],
        'representatives': representatives, 'stage_to_group': stage_to_group,
        'group_to_rep': group_to_rep, 'input_fingerprint': 'diamond-input',
        'deduplication': {'candidate_representative_count': 2},
    }


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.active = {'attrs': dict(attrs), 'text': ''}
            self.scripts.append(self.active)

    def handle_data(self, data):
        if self.active is not None:
            self.active['text'] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = None


def embedded_data(html):
    parser = Scripts()
    parser.feed(html)
    matches = [script for script in parser.scripts
               if script['attrs'].get('id') == 'execution-plan-data']
    assert len(matches) == 1
    return json.loads(matches[0]['text'])


@pytest.fixture
def visual_project(tmp_path, monkeypatch):
    root = tmp_path/'Reverie'
    (root/'api/TreeGroup').mkdir(parents=True)
    monkeypatch.setattr(api, 'API_DIR', root/'api')
    monkeypatch.setattr(api, 'REVERIE_ROOT', root)
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    return root


def test_payload_preserves_every_stage_and_both_join_dependencies():
    from api.dag_visualization import visualization_data
    plan = projection()
    data = visualization_data(plan)
    assert {stage['id'] for stage in data['stages']} == set('ABCD')
    assert len(data['stages']) == 4
    assert {tuple(edge) for edge in data['edges']} == {
        ('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')}
    join = next(stage for stage in data['stages'] if stage['id'] == 'D')
    assert set(join['predecessors']) == {'B', 'C'}
    assert data['stage_to_group'] == plan['stage_to_group']
    assert data['group_to_rep'] == plan['group_to_rep']
    assert data['counts']['group_count'] == 3
    assert data['counts']['representative_count'] == 2


def test_post_distinguishes_final_partition_from_candidates(visual_project):
    with TestClient(api.app) as client:
        initial = client.post('/visualize-execution-plan', json={
            'execution_plan': projection(), 'is_final': False})
        final = client.post('/visualize-execution-plan', json={
            'execution_plan': projection(True), 'is_final': True, 'simulation_id': 'run-final'})
    assert initial.status_code == final.status_code == 200
    a, b = embedded_data(initial.text), embedded_data(final.text)
    assert a['counts']['group_count'] == 3
    assert b['counts']['group_count'] == 2
    assert a['counts']['representative_count'] == b['counts']['representative_count'] == 2
    assert a['is_final'] is False and b['is_final'] is True
    assert b['simulation_id'] == 'run-final'
    assert b['stage_to_group'] == projection(True)['stage_to_group']
    assert 'no-store' in initial.headers['cache-control']
    assert final.headers['content-type'].startswith('text/html')


@pytest.mark.parametrize('corruption', [
    'missing_member', 'wrong_stage_map', 'wrong_rep_map', 'missing_rep_member',
    'unknown_edge', 'mismatched_count', 'cycle', 'missing_predecessor',
])
def test_post_rejects_inconsistent_partition_instead_of_drawing_it(visual_project, corruption):
    plan = projection()
    if corruption == 'missing_member':
        plan['groups'][2]['stage_ids'].remove('D')
    elif corruption == 'wrong_stage_map':
        plan['stage_to_group']['D'] = 'group2'
    elif corruption == 'wrong_rep_map':
        plan['group_to_rep']['group3'] = 'rep1'
    elif corruption == 'missing_rep_member':
        plan['representatives'][0]['member_group_ids'].remove('group2')
    elif corruption == 'unknown_edge':
        plan['edges'].append(['A', 'not-a-stage'])
    elif corruption == 'mismatched_count':
        plan['counts']['group_count'] = 99
    elif corruption == 'cycle':
        plan['edges'].append(['D', 'A'])
        plan['stages'][0]['predecessors'].append('D')
    elif corruption == 'missing_predecessor':
        plan['stages'][3]['predecessors'].remove('B')
    with TestClient(api.app) as client:
        response = client.post('/visualize-execution-plan', json={'execution_plan': plan})
    assert response.status_code == 400, response.text


def test_get_rebuilds_from_current_plan_and_ignores_old_three_group_html(visual_project):
    directory = visual_project/'api/TreeGroup'
    plan = projection(True)
    # plan_projection reads operation counts from the complete saved plan.
    for stage in plan['stages']:
        stage['operations'] = [{}]
    (directory/'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    (directory/'tree_split_3d.html').write_text(
        '<html>STALE_THREE_GROUPS<script id="subt-data">[1,2,3]</script></html>',
        encoding='utf-8')
    with TestClient(api.app) as client:
        response = client.get('/get-tree-groups-3d?output_dir=TreeGroup')
    assert response.status_code == 200, response.text
    assert 'STALE_THREE_GROUPS' not in response.text
    data = embedded_data(response.text)
    assert data['counts']['logical_unit_count'] == 4
    assert data['counts']['group_count'] == 2
    assert data['stage_to_group'] == plan['stage_to_group']
    assert {tuple(edge) for edge in data['edges']} == {tuple(edge) for edge in plan['edges']}
    assert 'no-store' in response.headers['cache-control']


def test_get_requires_a_current_plan_even_if_legacy_html_exists(visual_project):
    (visual_project/'api/TreeGroup/tree_split_3d.html').write_text('old three groups', encoding='utf-8')
    with TestClient(api.app) as client:
        response = client.get('/get-tree-groups-3d?output_dir=TreeGroup')
    assert response.status_code == 404
    assert response.text != 'old three groups'


def test_visualization_directory_cannot_escape_project(visual_project):
    outside = visual_project.parent/'outside'
    outside.mkdir()
    (outside/'tree_split_3d.html').write_text('outside secret', encoding='utf-8')
    with TestClient(api.app) as client:
        response = client.get('/get-tree-groups-3d', params={'output_dir': '../../outside'})
    assert response.status_code in (400, 403)
    assert 'outside secret' not in response.text


def test_stage_names_remain_json_data_and_scripts_load_from_local_api():
    from api.dag_visualization import render_execution_plan
    plan = projection()
    danger = '</script><script id="injected">alert(1)</script>&\u2028'
    plan['stages'][0]['id'] = danger
    for stage in plan['stages']:
        stage['predecessors'] = [danger if name == 'A' else name for name in stage['predecessors']]
    plan['stage_to_group'][danger] = plan['stage_to_group'].pop('A')
    plan['groups'][0]['stage_ids'] = [danger]
    plan['edges'] = [[danger if name == 'A' else name for name in edge] for edge in plan['edges']]
    html = render_execution_plan(plan, is_final=True, simulation_id='run</script>')
    data = embedded_data(html)
    assert data['stages'][0]['id'] == danger
    assert data['simulation_id'] == 'run</script>'
    parser = Scripts()
    parser.feed(html)
    assert not any(script['attrs'].get('id') == 'injected' for script in parser.scripts)
    sources = [script['attrs'].get('src') for script in parser.scripts if script['attrs'].get('src')]
    assert '/three.min.js' in sources and '/OrbitControls.js' in sources
    assert not any(source.startswith(('https://', 'http://')) for source in sources)
