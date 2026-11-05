"""Render the current stage DAG partition, never legacy TreeCut snapshots."""
from collections import deque
from copy import deepcopy
import json
from pathlib import Path


def _objects(values, label):
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label}不能为空")
    result = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"]:
            raise ValueError(f"{label}需要有效标识")
        if value["id"] in result:
            raise ValueError(f"{label}标识重复: {value['id']}")
        result[value["id"]] = deepcopy(value)
    return result


def visualization_data(plan, *, is_final=False, simulation_id=None):
    """Validate a plan_projection and derive the exact three displayed levels."""
    if not isinstance(plan, dict):
        raise ValueError("执行计划格式无效")
    stages = _objects(plan.get("stages"), "阶段")
    groups = _objects(plan.get("groups"), "子单元")
    representatives = _objects(plan.get("representatives"), "代表任务")
    if "Root" in stages:
        raise ValueError("Root不是逻辑阶段")
    stage_to_group = plan.get("stage_to_group")
    group_to_rep = plan.get("group_to_rep")
    if not isinstance(stage_to_group, dict) or set(stage_to_group) != set(stages):
        raise ValueError("阶段到子单元的映射不完整")
    if not isinstance(group_to_rep, dict) or set(group_to_rep) != set(groups):
        raise ValueError("子单元到代表任务的映射不完整")

    covered_stages = set()
    for gid, group in groups.items():
        members = group.get("stage_ids")
        if not isinstance(members, list) or not members:
            raise ValueError(f"子单元 {gid} 没有阶段")
        for sid in members:
            if not isinstance(sid, str) or sid not in stages or sid in covered_stages:
                raise ValueError("子单元阶段存在遗漏、重复或未知标识")
            if stage_to_group[sid] != gid:
                raise ValueError("阶段到子单元的映射不一致")
            covered_stages.add(sid)
    if covered_stages != set(stages):
        raise ValueError("子单元没有覆盖全部阶段")

    covered_groups = set()
    reused_units = 0
    for rid, representative in representatives.items():
        members = representative.get("member_group_ids")
        own_group = representative.get("group_id")
        if not isinstance(members, list) or not members or own_group not in members:
            raise ValueError(f"代表任务 {rid} 的子单元映射无效")
        for gid in members:
            if not isinstance(gid, str) or gid not in groups or gid in covered_groups:
                raise ValueError("代表任务的子单元存在遗漏、重复或未知标识")
            if group_to_rep[gid] != rid:
                raise ValueError("子单元到代表任务的映射不一致")
            covered_groups.add(gid)
            if gid != own_group:
                reused_units += len(groups[gid]["stage_ids"])
    if covered_groups != set(groups):
        raise ValueError("代表任务没有覆盖全部子单元")

    raw_edges = plan.get("edges")
    if not isinstance(raw_edges, list):
        raise ValueError("执行计划缺少DAG依赖")
    edges = []
    edge_set = set()
    predecessors = {sid: [] for sid in stages}
    successors = {sid: [] for sid in stages}
    for edge in raw_edges:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            raise ValueError("DAG依赖格式无效")
        source, target = edge
        if not isinstance(source, str) or not isinstance(target, str) or source not in stages or target not in stages:
            raise ValueError("DAG依赖指向未知阶段")
        if source == target or (source, target) in edge_set:
            raise ValueError("DAG依赖重复或自环")
        edge_set.add((source, target))
        edges.append([source, target])
        predecessors[target].append(source)
        successors[source].append(target)
    pending = {sid: len(parents) for sid, parents in predecessors.items()}
    ready = deque(sid for sid in stages if not pending[sid])
    roots = list(ready)
    depths = {sid: 0 for sid in roots}
    order = []
    while ready:
        sid = ready.popleft()
        order.append(sid)
        for child in successors[sid]:
            depths[child] = max(depths.get(child, 0), depths[sid] + 1)
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    if len(order) != len(stages):
        raise ValueError("阶段依赖包含环")
    for sid, stage in stages.items():
        parents = stage.get("predecessors")
        if parents is not None and (not isinstance(parents, list) or not all(isinstance(parent, str) for parent in parents)
                                    or len(parents) != len(set(parents)) or set(parents) != set(predecessors[sid])):
            raise ValueError("阶段前驱与DAG依赖不一致")
        gid = stage_to_group[sid]
        rid = group_to_rep[gid]
        if stage.get("group_id", gid) != gid or stage.get("representative_id", rid) != rid:
            raise ValueError("阶段的分组或代表任务信息不一致")
        operations = stage.get("operation_count", 0)
        if isinstance(operations, bool) or not isinstance(operations, int) or operations < 0:
            raise ValueError("阶段操作数量无效")
        stage.update(group_id=gid, representative_id=rid, predecessors=predecessors[sid],
                     operation_count=operations, depth=depths[sid])

    counts = {"logical_unit_count": len(stages), "group_count": len(groups),
              "representative_count": len(representatives), "reused_unit_count": reused_units,
              "reused_group_count": len(groups)-len(representatives)}
    supplied_counts = plan.get("counts")
    if not isinstance(supplied_counts, dict):
        raise ValueError("执行计划缺少数量信息")
    for key, value in counts.items():
        if key in supplied_counts and (isinstance(supplied_counts[key], bool) or supplied_counts[key] != value):
            raise ValueError(f"执行计划数量与分组不一致: {key}")
    group_edges = []
    group_edge_set = set()
    for source, target in edges:
        pair = (stage_to_group[source], stage_to_group[target])
        if pair[0] != pair[1] and pair not in group_edge_set:
            group_edges.append(list(pair))
            group_edge_set.add(pair)
    for gid, group in groups.items():
        parents = group.get("predecessors")
        expected = {source for source, target in group_edges if target == gid}
        if parents is not None and (not isinstance(parents, list) or not all(isinstance(parent, str) for parent in parents)
                                    or len(parents) != len(set(parents)) or set(parents) != expected):
            raise ValueError("子单元前驱与DAG依赖不一致")
        group["representative_id"] = group_to_rep[gid]

    return {"counts": counts, "stages": list(stages.values()), "edges": edges,
            "groups": list(groups.values()), "representatives": list(representatives.values()),
            "stage_to_group": deepcopy(stage_to_group), "group_to_rep": deepcopy(group_to_rep),
            "group_edges": group_edges, "roots": roots, "topological_order": order,
            "is_final": bool(is_final), "simulation_id": simulation_id,
            "input_fingerprint": plan.get("input_fingerprint"),
            "deduplication": deepcopy(plan.get("deduplication", {}))}


def render_execution_plan(plan, *, is_final=False, simulation_id=None):
    data = visualization_data(plan, is_final=is_final, simulation_id=simulation_id)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    encoded = (encoded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    template = Path(__file__).with_name("dag_visualization.html").read_text(encoding="utf-8")
    return template.replace("__EXECUTION_PLAN_JSON__", encoded)
