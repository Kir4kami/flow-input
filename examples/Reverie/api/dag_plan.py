"""Stage DAG planning and generic labelled input/resource graph equivalence.

Exact event-order mappings can be reused directly. Reordered mappings remain
provisional until independently validated for the frozen input, runtime and
mode. ECMP without a native oracle stays literal and fails closed.
"""
from collections import deque
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import time

import networkx as nx

try:
    from .dag_equivalence import build_input_graph, match_input_graphs, validated_native_routes
except ImportError:
    from dag_equivalence import build_input_graph, match_input_graphs, validated_native_routes

SCHEMA_VERSION = 1


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def natural_key(value):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(value))]


def _delay(value):
    match = re.fullmatch(r"([0-9.]+)(s|ms|us|ns|ps)?", value)
    if not match:
        raise ValueError(f"Invalid link delay: {value}")
    units = {"s": 1000000000, "ms": 1000000, "us": 1000, "ns": 1, "ps": Decimal("0.001")}
    return str((Decimal(match[1]) * units[match[2] or "s"]).normalize())


class Topology:
    def __init__(self, data):
        self.data = data
        self.graph = nx.Graph()
        for node in data["nodes"]:
            self.graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
        for link in data["links"]:
            self.graph.add_edge(link["src"], link["dst"], **{k: v for k, v in link.items() if k not in ("src", "dst")})
        self._distance = {}

    @classmethod
    def read(cls, path):
        lines = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        if len(lines) < 2:
            raise ValueError("Topology file has no header/switch list")
        header = list(map(int, lines[0].split()))
        if len(header) < 4:
            raise ValueError("Topology header requires node/switch/leaf/link counts")
        n, switch_count, leaves, link_count = header[:4]
        switches = list(map(int, lines[1].split()))
        if len(switches) != switch_count or len(lines[2:]) != link_count:
            raise ValueError("Topology switch/link counts do not match its contents")
        roles = {node: ("leaf" if index < leaves else "spine") for index, node in enumerate(switches)}
        data = {"nodes": [{"id": node, "role": roles.get(node, "host")} for node in range(n)], "links": []}
        edges = set()
        for line in lines[2:]:
            fields = line.split()
            if len(fields) != 5:
                raise ValueError(f"Invalid topology link: {line}")
            a, b = map(int, fields[:2])
            if a == b or min(a, b) < 0 or max(a, b) >= n:
                raise ValueError("Topology link refers to an invalid node")
            pair = tuple(sorted((a, b)))
            if pair in edges:
                raise ValueError("Parallel physical links require an explicit route/port model")
            edges.add(pair)
            data["links"].append({"src": a, "dst": b, "bandwidth": fields[2],
                                  "delay_ns": _delay(fields[3]), "error_rate": str(Decimal(fields[4]).normalize())})
        return cls(data)

    def distances(self, destination):
        if destination not in self._distance:
            # Hosts cannot forward packets, matching sim.cc CalculateRoute.
            distance = {destination: 0}
            queue = deque([destination])
            while queue:
                node = queue.popleft()
                for neighbor in sorted(self.graph.neighbors(node)):
                    if neighbor not in distance:
                        distance[neighbor] = distance[node] + 1
                        if self.graph.nodes[neighbor]["role"] != "host":
                            queue.append(neighbor)
            self._distance[destination] = distance
        return self._distance[destination]

    def route(self, source, destination):
        if source not in self.graph or destination not in self.graph:
            raise ValueError(f"Flow endpoint absent from topology: {source}->{destination}")
        if self.graph.nodes[source]["role"] != "host" or self.graph.nodes[destination]["role"] != "host":
            raise ValueError("Flow endpoints must be hosts")
        if source == destination:
            return [source], set(), False
        distance = self.distances(destination)
        if source not in distance:
            raise ValueError(f"Unreachable flow: {source}->{destination}")
        frontier = [source]
        visited = set()
        links = set()
        ambiguous = False
        while frontier:
            node = frontier.pop()
            if node in visited or node == destination:
                continue
            visited.add(node)
            choices = [v for v in sorted(self.graph.neighbors(node))
                       if distance.get(v) == distance[node] - 1]
            ambiguous |= len(choices) != 1
            for next_node in choices:
                links.add((node, next_node))
                frontier.append(next_node)
        if ambiguous:
            return None, links, True
        path = [source]
        while path[-1] != destination:
            node = path[-1]
            path.append(next(v for v in self.graph.neighbors(node) if distance.get(v) == distance[node] - 1))
        return path, links, False

    def node_attributes(self, node):
        incident = sorted(_json({"peer_role": self.graph.nodes[peer]["role"], **attrs})
                          for peer, attrs in self.graph[node].items())
        return {"role": self.graph.nodes[node]["role"], "degree": self.graph.degree(node), "incident": incident}


def read_operations(directory, stage_id):
    paths = sorted(Path(directory).glob("rdma_operate*.txt"), key=lambda p: natural_key(p.name))
    operations = []
    index_map = {}
    for index, path in enumerate(paths):
        match = re.fullmatch(r"rdma_operate(\d*)\.txt", path.name)
        if not match:
            continue
        original_index = int(match[1] or 0)
        if original_index in index_map:
            raise ValueError(f"Duplicate operation index in {directory}: {original_index}")
        operation_id = f"{stage_id}:op{len(operations)}"
        index_map[original_index] = operation_id
        phases = []
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("stat"):
                continue
            if line.startswith("phase"):
                phases.append([])
                continue
            tokens = line.split()
            if len(tokens) != 14 or tokens[:2] != ["Type", "rdma_send"]:
                raise ValueError(f"Invalid flow record {path}:{number}")
            values = dict(zip(tokens[2::2], tokens[3::2]))
            try:
                flow = {"src": int(values["src_node"]), "dst": int(values["dst_node"]),
                        "sport": int(values["src_port"]), "dport": int(values["dst_port"]),
                        "priority": int(values["priority"]), "msg_len": int(values["msg_len"])}
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Invalid flow values {path}:{number}") from exc
            if (min(flow.values()) < 0 or flow["msg_len"] == 0
                    or flow["priority"] >= 8 or max(flow["sport"], flow["dport"]) > 65535):
                raise ValueError(f"Invalid unsigned flow field {path}:{number}")
            if not phases:
                raise ValueError(f"Flow before its phase header: {path}:{number}")
            phases[-1].append(flow)
        operations.append({"id": operation_id, "index": len(operations), "source_file": str(path.resolve()),
                           "phases": phases, "predecessors": []})
    dependency = Path(directory) / "dependence.txt"
    if dependency.exists():
        graph = nx.DiGraph()
        graph.add_nodes_from(operation["id"] for operation in operations)
        for raw in dependency.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"(\d+)(?:-(\d+))?\s*:\s*(\d+)(?:-(\d+))?", line)
            if not match:
                raise ValueError(f"Invalid operation dependency: {line}")
            a, b, c, d = match.groups()
            for dependent in range(int(a), int(b or a) + 1):
                for predecessor in range(int(c), int(d or c) + 1):
                    if dependent not in index_map or predecessor not in index_map:
                        raise ValueError("Operation dependency refers to an absent operation")
                    graph.add_edge(index_map[predecessor], index_map[dependent])
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError("Operation dependencies contain a cycle")
        for operation in operations:
            operation["predecessors"] = sorted(graph.predecessors(operation["id"]))
    return operations


def _stage_graph(plan):
    graph = nx.DiGraph()
    graph.add_nodes_from(stage["id"] for stage in plan["stages"])
    graph.add_edges_from(plan["edges"])
    return graph


def _set_groups(plan, members):
    order = {stage["id"]: index for index, stage in enumerate(plan["stages"])}
    flattened = [stage for group in members for stage in group]
    if set(flattened) != set(order) or len(flattened) != len(order) or any(not group for group in members):
        raise ValueError("Groups must partition every stage exactly once")
    members = [sorted(group, key=order.get) for group in members]
    members.sort(key=lambda group: min(order[stage] for stage in group))
    while True:
        owner = {stage: index for index, group in enumerate(members) for stage in group}
        quotient = nx.DiGraph()
        quotient.add_nodes_from(range(len(members)))
        quotient.add_edges_from((owner[a], owner[b]) for a, b in plan["edges"] if owner[a] != owner[b])
        components = list(nx.strongly_connected_components(quotient))
        if all(len(component) == 1 for component in components):
            break
        members = [sorted([stage for index in sorted(component) for stage in members[index]], key=order.get)
                   for component in components]
        members.sort(key=lambda group: min(order[stage] for stage in group))
    plan["groups"] = [{"id": f"group{index + 1}", "stage_ids": group, "predecessors": []}
                      for index, group in enumerate(members)]
    plan["stage_to_group"] = {stage: group["id"] for group in plan["groups"] for stage in group["stage_ids"]}
    for group in plan["groups"]:
        group["predecessors"] = sorted({plan["stage_to_group"][a] for a, b in plan["edges"]
                                         if b in group["stage_ids"] and a not in group["stage_ids"]}, key=natural_key)


def match_groups(plan, source_group, target_group, releases=None, allow_provisional=False, mode=None):
    """Prove an input mapping, or return a gated event-order candidate.

    Multi-stage groups require every relative boundary release explicitly. This
    method never uses simulation output as an equivalence attribute.
    """
    topology = Topology(plan["topology"])
    mode = mode or plan.get("equivalence_mode","packet")
    if mode not in ("packet","mixed"): raise ValueError("Equivalence mode must be packet or mixed")
    native_routes = validated_native_routes(plan)
    for strict_order in ((True,False) if allow_provisional else (True,)):
        options = {"strict_order":strict_order,"native_routes":native_routes,
                   "literal_input":mode=="mixed" and not allow_provisional}
        source = build_input_graph(plan,source_group,topology,releases,**options)
        target = build_input_graph(plan,target_group,topology,releases,**options)
        mapping = match_input_graphs(source,target)
        if mapping is not None:
            required = mapping["mixed_verification_required"] if mode=="mixed" else mapping["verification_required"]
            mapping["equivalence_status"] = "provisional" if required else "proven"
            mapping["proof_mode"] = mode
            return mapping
    return None


def deduplicate_plan(plan, enabled=True, releases=None, allow_provisional=False, mode=None):
    started = time.monotonic()
    search_budget_seconds = 10
    deadline = started+search_budget_seconds
    budget_exhausted = False
    plan = deepcopy(plan)
    mode = mode or plan.get("equivalence_mode","packet")
    if mode not in ("packet","mixed"): raise ValueError("Equivalence mode must be packet or mixed")
    plan["equivalence_mode"] = mode
    releases = releases if releases is not None else plan.get("boundary_releases", {})
    if any(isinstance(value,bool) or not isinstance(value,int) or value < 0 for value in releases.values()):
        raise ValueError("Boundary releases must be exact nonnegative integer nanoseconds")
    plan["boundary_releases"] = dict(releases)
    plan["deduplicate_enabled"] = bool(enabled)
    plan["allow_provisional"] = bool(allow_provisional)
    representatives = []; groups = {g["id"]:g for g in plan["groups"]}
    topology = Topology(plan["topology"])
    native_routes = validated_native_routes(plan)
    models = {}
    def model(group,strict):
        key = (group["id"],strict)
        if key not in models:
            models[key] = build_input_graph(plan,group,topology,releases,strict_order=strict,native_routes=native_routes,
                                           literal_input=mode=="mixed" and not allow_provisional)
        return models[key]
    def identity(group):
        stage_map = {sid:sid for sid in group["stage_ids"]}
        stages = {stage["id"]:stage for stage in plan["stages"]}
        operation_map = {sid:{str(op["index"]):op["index"] for op in stages[sid]["operations"]}
                         for sid in group["stage_ids"]}
        phase_map = {sid:{str(op["index"]):{str(i):i for i in range(len(op["phases"]))}
                         for op in stages[sid]["operations"]} for sid in group["stage_ids"]}
        flow_map = {sid:{str(op["index"]):{str(i):{str(j):j for j in range(len(phase))}
                         for i,phase in enumerate(op["phases"])} for op in stages[sid]["operations"]}
                    for sid in group["stage_ids"]}
        operations = {op["id"]:op["id"] for sid in group["stage_ids"] for op in stages[sid]["operations"]}
        return {"stage_map":stage_map,"operation_map":operation_map,"phase_map":phase_map,"flow_map":flow_map,
                "node_map":{},"port_map":{},"stages":stage_map,"operations":operations,"hosts":{},"ports":{},
                "verification_required":False,"equivalence_status":"proven",
                "mixed_verification_required":False,"proof_mode":mode,"certificate_kind":"identity"}
    for group in plan["groups"]:
        representative = None; mapping = None
        if enabled:
            for strict in ((True,False) if allow_provisional else (True,)):
                if time.monotonic() >= deadline:
                    budget_exhausted = True; break
                target = model(group,strict)
                for candidate in representatives:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        budget_exhausted = True; break
                    source = model(groups[candidate["group_id"]],strict)
                    mapping = match_input_graphs(source,target,budget_seconds=deadline-time.monotonic())
                    if mapping is not None:
                        representative = candidate; break
                if representative is not None: break
        if representative is None:
            representative = {"id": f"rep{len(representatives) + 1}", "group_id": group["id"],
                              "member_group_ids":[],"mappings":{},
                              "input_fingerprint":_digest({"experiment":plan["experiment_fingerprint"],
                                  "stages":[stage for stage in plan["stages"] if stage["id"] in group["stage_ids"]],
                                  "releases":{sid:releases.get(sid,0) for sid in group["stage_ids"]}}),
                              "equivalence":"labelled_input_and_route_graph",
                              "equivalence_status":"proven","verification_required":False,
                              "mixed_verification_required":False}
            representatives.append(representative)
            mapping = identity(group)
        representative["member_group_ids"].append(group["id"])
        mapping["proof_mode"] = mode
        required = mapping["mixed_verification_required"] if mode=="mixed" else mapping["verification_required"]
        mapping["equivalence_status"] = "provisional" if required else "proven"
        if mapping["verification_required"]:
            representative["verification_required"] = True
        if mapping["mixed_verification_required"]:
            representative["mixed_verification_required"] = True
        if required:
            representative["equivalence_status"] = "provisional"
        representative["mappings"][group["id"]] = mapping
    plan["representatives"] = representatives
    plan["group_to_rep"] = {group: rep["id"] for rep in representatives for group in rep["member_group_ids"]}
    reused = sum(len(groups[gid]["stage_ids"]) for rep in representatives
                 for gid in rep["member_group_ids"] if gid != rep["group_id"])
    plan["counts"] = {"logical_unit_count": len(plan["stages"]), "group_count": len(plan["groups"]),
                      "representative_count": len(representatives), "reused_unit_count": reused,
                      "reused_group_count": len(plan["groups"]) - len(representatives)}
    plan["input_fingerprint"] = _digest({"experiment": plan["experiment_fingerprint"], "edges": plan["edges"],
        "units": [{"id": stage["id"], "operations": stage["operations"]} for stage in plan["stages"]],
        "groups": plan["groups"], "boundary_releases": releases})
    provisional_count = sum(mapping.get("equivalence_status")=="provisional" for rep in representatives
                            for mapping in rep["mappings"].values())
    certificate = plan.get("route_certificate") or {}
    if not isinstance(certificate,dict): certificate = {}
    plan["deduplication"] = {"algorithm":"labelled_input_route_graph_v1",
        "provisional_allowed":bool(allow_provisional),"provisional_member_group_count":provisional_count,
        "requires_mode_validation":bool(provisional_count),
        "route_certificate_status":"native" if native_routes else "unique_or_literal",
        "search_policy":"bounded_fail_closed","search_budget_seconds":search_budget_seconds,
        "search_budget_exhausted":budget_exhausted}
    plan["equivalence_context"] = {"input_fingerprint":plan["input_fingerprint"],
        "experiment_fingerprint":plan["experiment_fingerprint"],
        "native_binary_sha256":certificate.get("native_binary_sha256") or plan.get("native_binary_sha256"),
        "native_runtime_sha256":certificate.get("native_runtime_sha256") or plan.get("native_runtime_sha256"),
        "mode":plan.get("equivalence_mode","packet")}
    return plan


def build_plan(tree_data, rdma_root, topology_file=None, config_file=None, groups=None,
               boundary_releases=None, deduplicate=True, topology_path=None):
    topology_file = topology_file or topology_path
    if not topology_file:
        raise ValueError("A topology file is required")
    root = Path(rdma_root).resolve()
    topology_file = Path(topology_file).resolve()
    topology = Topology.read(topology_file)
    graph = nx.DiGraph()
    metadata = {}
    for data in tree_data.get("nodes", []):
        sid = str(data["name"])
        if sid == "Root": continue
        if sid in metadata: raise ValueError(f"Duplicate stage: {sid}")
        if not sid or Path(sid).name != sid or sid in (".", "..") or "/" in sid or "\\" in sid:
            raise ValueError("Stage names must be local directory names")
        graph.add_node(sid); metadata[sid] = data
    edges = []
    for edge in tree_data.get("edges", []):
        a = edge.get("from_node", edge.get("from")); b = edge.get("to_node", edge.get("to"))
        if a == "Root":
            if b not in graph: raise ValueError(f"Dependency refers to an unknown stage: {b}")
            continue
        if a not in graph or b not in graph:
            raise ValueError(f"Dependency refers to an unknown stage: {a}->{b}")
        graph.add_edge(a,b)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Communication graph contains a cycle")
    order = list(nx.lexicographical_topological_sort(graph, key=natural_key))
    stages = []
    for sid in order:
        directory = (root / sid).resolve()
        try: directory.relative_to(root)
        except ValueError: raise ValueError("Stage input escapes the load directory")
        if not directory.is_dir():
            raise ValueError(f"Missing stage input directory: {sid}")
        operations = read_operations(directory, sid)
        resources = set()
        for operation in operations:
            for phase in operation["phases"]:
                for flow in phase:
                    for source, destination in ((flow["src"],flow["dst"]),(flow["dst"],flow["src"])):
                        path, links, ambiguous = topology.route(source,destination)
                        resources.add(f"host:{source}"); resources.add(f"host:{destination}")
                        for a,b in links:
                            resources.add(f"link:{a}>{b}")
                            if topology.graph.nodes[a]["role"] != "host": resources.add(f"switch_pool:{a}")
                            if topology.graph.nodes[b]["role"] != "host": resources.add(f"switch_pool:{b}")
        stages.append({"id":sid,"type":metadata[sid].get("type","OP"),
                       "operation_files":[op["source_file"] for op in operations], "operations":operations,
                       "predecessors":sorted(graph.predecessors(sid),key=natural_key),
                       "resources":sorted(resources), "empty":not any(phase for op in operations for phase in op["phases"])})
    config = Path(config_file).resolve() if config_file else None
    config_text = config.read_text(encoding="utf-8") if config else ""
    plan = {"schema_version":SCHEMA_VERSION,"tree_data":deepcopy(tree_data),"rdma_root":str(root),
            "topology_file":str(topology_file),"config_file":str(config) if config else None,
            "topology":topology.data,"topology_text":topology_file.read_text(encoding="utf-8"),"config_text":config_text,"stages":stages,
            "edges":[list(edge) for edge in graph.edges()],"empty_network":True,
            "experiment_fingerprint":_digest({"topology":topology.data,"config":config_text,"empty_network":True})}
    _set_groups(plan, groups or [[sid] for sid in order])
    return deduplicate_plan(plan, deduplicate, boundary_releases)


def schedule_stages(plan, durations):
    graph = _stage_graph(plan)
    windows = {}
    for sid in nx.topological_sort(graph):
        if sid not in durations:
            raise ValueError(f"Missing stage duration: {sid}")
        duration = int(durations[sid])
        if duration < 0: raise ValueError("A stage duration cannot be negative")
        start = max((windows[parent]["finish_ns"] for parent in graph.predecessors(sid)),default=0)
        windows[sid] = {"start_ns":start,"finish_ns":start+duration,"duration_ns":duration}
    return windows


def _window(value):
    if isinstance(value, dict): return int(value["start_ns"]),int(value.get("finish_ns",value.get("end_ns")))
    return int(value[0]),int(value[1])


def find_cross_group_conflicts(plan, stage_windows):
    windows = {}
    for stage in plan["stages"]:
        sid = stage["id"]
        if sid not in stage_windows:
            raise ValueError(f"Missing stage window: {sid}")
        start, finish = _window(stage_windows[sid])
        if start < 0 or finish < start:
            raise ValueError("Invalid stage window")
        windows[sid] = (start, finish)
    conflicts = []
    for index, a in enumerate(plan["stages"]):
        a_start, a_end = windows[a["id"]]
        for b in plan["stages"][index + 1:]:
            if plan["stage_to_group"][a["id"]] == plan["stage_to_group"][b["id"]]:
                continue
            b_start, b_end = windows[b["id"]]
            if (min(a_end, b_end) > max(a_start, b_start)
                    and set(a["resources"]).intersection(b["resources"])):
                conflicts.append((a["id"], b["id"]))
    return conflicts


def merge_groups(plan, pairs):
    result = deepcopy(plan)
    members = [set(group["stage_ids"]) for group in plan["groups"]]
    for a,b in pairs:
        if a not in plan["stage_to_group"] or b not in plan["stage_to_group"]:
            raise ValueError("Conflict refers to an unknown stage")
        left = next(group for group in members if a in group)
        right = next(group for group in members if b in group)
        if left is not right:
            left.update(right); members.remove(right)
    _set_groups(result, [list(group) for group in members])
    return deduplicate_plan(result,result.get("deduplicate_enabled",True))


def refine_groups(plan, conflicts_or_windows):
    conflicts = (find_cross_group_conflicts(plan,conflicts_or_windows)
                 if isinstance(conflicts_or_windows,dict) else conflicts_or_windows)
    return merge_groups(plan, conflicts)
