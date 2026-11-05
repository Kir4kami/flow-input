"""Persistence and API projections for stage DAG execution plans."""
import json
from pathlib import Path

from .dag_plan import build_plan, deduplicate_plan
from .dag_routes import collect_plan_routes


def plan_projection(plan):
    stages = []
    for stage in plan['stages']:
        group = plan['stage_to_group'][stage['id']]
        stages.append({
            'id': stage['id'], 'type': stage.get('type', ''),
            'predecessors': stage.get('predecessors', []),
            'group_id': group, 'representative_id': plan['group_to_rep'][group],
            'operation_count': len(stage.get('operations', [])),
        })
    return {
        'counts': plan['counts'], 'stages': stages, 'edges': plan['edges'],
        'groups': plan['groups'],
        'representatives': [{k: rep[k] for k in ('id', 'group_id', 'member_group_ids',
                                               'equivalence', 'equivalence_status',
                                               'verification_required') if k in rep}
                            for rep in plan['representatives']],
        'stage_to_group': plan['stage_to_group'], 'group_to_rep': plan['group_to_rep'],
        'input_fingerprint': plan.get('input_fingerprint'),
        'deduplication': plan.get('deduplication', {}),
        'route_evidence': {key: plan.get('route_certificate', {}).get(key)
                           for key in ('status', 'certified', 'reason', 'native_runtime_sha256')},
    }


def save_plan(tree_data, rdma_root, reverie_root, api_dir, output_dir='TreeGroup',
              enable_cut=True, deduplicate=True):
    reverie_root, api_dir = Path(reverie_root), Path(api_dir)
    directory = (api_dir / output_dir).resolve()
    directory.relative_to(api_dir.resolve())
    root = Path(rdma_root).resolve()
    root.relative_to(reverie_root.resolve())
    topology = reverie_root / 'leaf-spine.txt'
    config = reverie_root / 'config-workload.txt'
    groups = None
    if not enable_cut:
        groups = [[node['name'] for node in tree_data['nodes'] if node['name'] != 'Root']]
    plan = build_plan(tree_data, root, topology, config_file=config, groups=groups,
                      deduplicate=False)
    directory.mkdir(parents=True, exist_ok=True)
    plan = collect_plan_routes(plan, reverie_root.parent.parent, output_dir=directory)
    plan = deduplicate_plan(plan, enabled=deduplicate)
    if deduplicate and len(plan['groups']) > 1:
        candidate = deduplicate_plan(plan, enabled=True, allow_provisional=True)
        plan.setdefault('deduplication', {})['candidate_representative_count'] = candidate['counts']['representative_count']
        plan['deduplication']['strict_representative_count'] = plan['counts']['representative_count']
    (directory / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    original_nodes = {n['name']: n for n in tree_data['nodes']}
    overview = {'total_groups': len(plan['groups']), 'groups': [],
                'output_directory': str(directory), 'dependencies': plan['edges']}
    for index, group in enumerate(plan['groups'], 1):
        members = set(group['stage_ids'])
        edges = [{'from': a, 'to': b} for a, b in plan['edges'] if a in members and b in members]
        incoming = {edge['to'] for edge in edges}
        edges += [{'from': 'Root', 'to': stage} for stage in group['stage_ids'] if stage not in incoming]
        data = {'nodes': [{'name': 'Root', 'type': 'Root', 'layer': 0}] +
                         [original_nodes[stage] for stage in group['stage_ids']],
                'edges': edges, 'group_id': group['id'],
                'representative_id': plan['group_to_rep'][group['id']]}
        filename = f'tree_group_{index}.json'
        (directory / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        overview['groups'].append({'group_id': index, 'filename': filename,
                                   'filepath': str(directory / filename),
                                   'node_count': len(data['nodes']), 'edge_count': len(edges)})
    # The overview is authoritative; remove obsolete group JSON files only.
    for stale in directory.glob('tree_group_[0-9]*.json'):
        if stale.name not in {g['filename'] for g in overview['groups']}:
            stale.unlink()
    (directory / 'tree_group_overview.json').write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding='utf-8')
    (directory / 'Out_Dependence_Info.json').write_text(json.dumps(plan['edges'], ensure_ascii=False, indent=2), encoding='utf-8')
    # Derived HTML is refreshed along with the plan; request handlers also render
    # directly from the plan so pre-existing legacy files cannot show stale cuts.
    from .dag_visualization import render_execution_plan
    (directory / 'tree_split_3d.html').write_text(
        render_execution_plan(plan_projection(plan)), encoding='utf-8')
    return plan, overview, str((directory / 'plan.json').relative_to(api_dir)), directory


def load_plan(api_dir, plan_file):
    path = (Path(api_dir) / plan_file).resolve()
    path.relative_to(Path(api_dir).resolve())
    if path.name != 'plan.json':
        raise ValueError('请选择切分步骤生成的 plan.json')
    plan = json.loads(path.read_text(encoding='utf-8'))
    return plan
