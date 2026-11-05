"""Input graph isomorphisms, with an explicit gate for event-order changes.

An isomorphism is an input certificate, never a comparison of simulation output.
Changing same-time event submission order is only a provisional candidate. Such
candidates require independent validation for the exact input, binary and mode.
"""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import threading
import time

import networkx as nx


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),ensure_ascii=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def flow_key(flow):
    return ",".join(str(flow[key]) for key in ("src", "dst", "sport", "dport"))


@dataclass
class InputGraph:
    graph: object
    group: dict
    operations: dict
    stages: dict
    strict_order: bool
    fingerprint: str


def validated_native_routes(plan):
    certificate = plan.get("route_certificate") or {}
    if not isinstance(certificate,dict): return {}
    if (certificate.get("schema_version") != 1 or certificate.get("certified") is not True
            or certificate.get("oracle") != "native" or not certificate.get("native_binary_sha256")
            or not certificate.get("native_runtime_sha256")
            or certificate.get("topology_fingerprint") != _digest(plan["topology"])
            or certificate.get("experiment_fingerprint") != plan.get("experiment_fingerprint")):
        return {}
    try:
        try:
            from .dag_routes import validate_native_routes
        except ImportError:
            from dag_routes import validate_native_routes
        flows = {flow_key(flow):flow for stage in plan["stages"] for op in stage["operations"]
                 for phase in op["phases"] for flow in phase}
        validate_native_routes(certificate,flows,plan["topology"])
    except (ImportError,ValueError,TypeError,KeyError,OverflowError,AttributeError):
        return {}
    return certificate["routes"]


def _checked_path(topology, path, source, destination):
    if (not isinstance(path,list) or not path
            or any(isinstance(node,bool) or not isinstance(node,int) for node in path)
            or path[0] != source or path[-1] != destination or len(path) != len(set(path))):
        return None
    if any(a not in topology.graph or b not in topology.graph[a] for a,b in zip(path,path[1:])):
        return None
    return path


def build_input_graph(plan, group, topology, releases=None, *, strict_order=True, native_routes=None, literal_input=False):
    """Encode dependencies, QP identity, routes, shared resources and launch order.

    Only used physical nodes are expanded; each includes the complete incident
    interface environment, including idle links that affect shared pool sizes.
    ECMP without a matching native certificate pins all physical and port IDs.
    """
    releases = releases if releases is not None else plan.get("boundary_releases", {})
    for sid in group["stage_ids"]:
        value = releases.get(sid,0)
        if isinstance(value,bool) or not isinstance(value,int) or value < 0:
            raise ValueError("Boundary releases must be exact nonnegative integer nanoseconds")
    if len(group["stage_ids"]) > 1 and any(sid not in releases for sid in group["stage_ids"]):
        return None
    stages = {stage["id"]:stage for stage in plan["stages"]}
    operations = {op["id"]:(sid,op) for sid in group["stage_ids"] for op in stages[sid]["operations"]}
    native = validated_native_routes(plan) if native_routes is None else native_routes
    routes = {}
    literal = literal_input or any(Decimal(link["error_rate"]) != 0 for link in plan["topology"]["links"])
    for sid in group["stage_ids"]:
        for op in stages[sid]["operations"]:
            for phase in op["phases"]:
                for flow in phase:
                    key = flow_key(flow)
                    record = native.get(key, {})
                    forward = _checked_path(topology,record.get("forward"),flow["src"],flow["dst"])
                    reverse = _checked_path(topology,record.get("reverse"),flow["dst"],flow["src"])
                    if forward is None or reverse is None:
                        fwd,flinks,famb = topology.route(flow["src"],flow["dst"])
                        rev,rlinks,ramb = topology.route(flow["dst"],flow["src"])
                        if famb or ramb:
                            literal = True
                            routes[key] = (None,None,flinks,rlinks)
                            continue
                        forward,reverse = fwd,rev
                    routes[key] = (forward,reverse,set(zip(forward,forward[1:])),set(zip(reverse,reverse[1:])))
    graph = nx.MultiDiGraph()
    used = set()
    data_resources = {}
    def node(key, kind, **attributes):
        graph.add_node(key,color=_json({"kind":kind,**attributes}))
        return key
    def edge(a,b,relation):
        graph.add_edge(a,b,relation=relation)
    def physical(value):
        used.add(value)
        key = ("physical",value)
        if key not in graph:
            node(key,"physical",environment=topology.node_attributes(value),literal=value if literal else None)
        return key
    def port(value):
        key = ("port",value)
        if key not in graph: node(key,"port",literal=value if literal else None)
        return key
    for stage_index,sid in enumerate(group["stage_ids"]):
        stage = stages[sid]
        stage_node = node(("stage",sid),"stage",release_ns=int(releases.get(sid,0)),
                          order=stage_index if strict_order else None)
        for parent in stage["predecessors"]:
            if parent in group["stage_ids"]: edge(("stage",parent),stage_node,"stage_dependency")
        for op_position,op in enumerate(stage["operations"]):
            op_node = node(("operation",sid,op["index"]),"operation",
                           order=op_position if strict_order else None)
            edge(stage_node,op_node,"contains_operation")
            for parent in op["predecessors"]:
                parent_stage,parent_op = operations[parent]
                edge(("operation",parent_stage,parent_op["index"]),op_node,"operation_dependency")
            op_resources = set()
            for phase_index,phase in enumerate(op["phases"]):
                phase_node = node(("phase",sid,op["index"],phase_index),"phase",index=phase_index)
                edge(op_node,phase_node,"contains_phase")
                if phase_index:
                    edge(("phase",sid,op["index"],phase_index-1),phase_node,"next_phase")
                phase_nodes = []
                phase_resources = []
                for flow_index,flow in enumerate(phase):
                    flow_node = node(("flow",sid,op["index"],phase_index,flow_index),"flow",
                                     size=flow["msg_len"],priority=flow["priority"],
                                     order=flow_index if strict_order else None)
                    edge(phase_node,flow_node,"contains_flow")
                    edge(flow_node,physical(flow["src"]),"source")
                    edge(flow_node,physical(flow["dst"]),"destination")
                    edge(flow_node,port(flow["sport"]),"source_port")
                    edge(flow_node,port(flow["dport"]),"destination_port")
                    forward,reverse,flinks,rlinks = routes[flow_key(flow)]
                    for direction,path,links in (("data",forward,flinks),("ack",reverse,rlinks)):
                        if path is not None:
                            for position,value in enumerate(path):
                                edge(flow_node,physical(value),f"{direction}_hop_{position}")
                        else:
                            # Ambiguous routes are literal. Retain every possible
                            # directed resource; do not invent a chosen ECMP path.
                            for a,b in sorted(links):
                                resource = ("potential_link",direction,a,b)
                                if resource not in graph:
                                    node(resource,"potential_link",direction=direction,a=a,b=b)
                                    edge(resource,physical(a),"from");edge(resource,physical(b),"to")
                                edge(flow_node,resource,"potential_route")
                    resources = {("source_nic",flow["src"])} | {("data_egress",a,b) for a,b in flinks}
                    phase_nodes.append(flow_node);phase_resources.append(resources)
                    op_resources.update(resources)
                # These order constraints cannot be waived by packet validation:
                # a shared sender/data egress makes launch order part of input.
                for i,left in enumerate(phase_nodes):
                    for j in range(i+1,len(phase_nodes)):
                        if phase_resources[i] & phase_resources[j]: edge(left,phase_nodes[j],"launch_before")
            data_resources[op_node] = op_resources
    # The simulator checks runnable operations in flattened input order. Keep
    # this order when their traffic can contend, including later phases.
    op_nodes = list(data_resources)
    for i,left in enumerate(op_nodes):
        for right in op_nodes[i+1:]:
            if data_resources[left] & data_resources[right]: edge(left,right,"operation_launch_before")
    for link in plan["topology"]["links"]:
        a,b = link["src"],link["dst"]
        if a in used and b in used:
            relation = "physical_link:"+_json({k:v for k,v in link.items() if k not in ("src","dst")})
            edge(("physical",a),("physical",b),relation);edge(("physical",b),("physical",a),relation)
    signature = _digest({"nodes":sorted(Counter(data["color"] for _,data in graph.nodes(data=True)).items()),
                         "edges":sorted(Counter(data["relation"] for *_,data in graph.edges(data=True)).items())})
    return InputGraph(graph,group,operations,stages,strict_order,signature)


class _SearchLimit(Exception):
    pass


_MATCH_LOCK = threading.RLock()


class _Matcher(nx.algorithms.isomorphism.MultiDiGraphMatcher):
    def __init__(self,a,b,budget_seconds=3):
        super().__init__(a,b,node_match=lambda x,y:x["color"]==y["color"],
                         edge_match=nx.algorithms.isomorphism.categorical_multiedge_match("relation",None))
        self.visits = 0
        self.deadline = time.monotonic()+min(3,max(0,budget_seconds))

    def semantic_feasibility(self,a,b):
        self.visits += 1
        if self.visits > 200000 or (self.visits%256 == 0 and time.monotonic()>self.deadline):
            raise _SearchLimit()
        return super().semantic_feasibility(a,b)


def _match_input_graphs(source,target,budget_seconds):
    if source is None or target is None or source.fingerprint != target.fingerprint:
        return None
    matcher = _Matcher(source.graph,target.graph,budget_seconds)
    try:
        if not matcher.is_isomorphic(): return None
        mapping = dict(matcher.mapping)
    except _SearchLimit:
        return None  # An incomplete proof always means independent simulation.
    finally:
        matcher.reset_recursion_limit()
    stage_map = {};op_map = {};phase_map = {};flow_map = {};nodes = {};ports = {};operation_ids = {}
    provisional = not source.strict_order
    for a,b in mapping.items():
        if a[0] == "stage": stage_map[a[1]] = b[1]
        elif a[0] == "operation":
            op_map.setdefault(a[1],{})[str(a[2])] = b[2]
            operation_ids[source.stages[a[1]]["operations"][a[2]]["id"]] = target.stages[b[1]]["operations"][b[2]]["id"]
        elif a[0] == "phase":
            phase_map.setdefault(a[1],{}).setdefault(str(a[2]),{})[str(a[3])] = b[3]
        elif a[0] == "flow":
            flow_map.setdefault(a[1],{}).setdefault(str(a[2]),{}).setdefault(str(a[3]),{})[str(a[4])] = b[4]
        elif a[0] == "physical": nodes[str(a[1])] = b[1]
        elif a[0] == "port": ports[str(a[1])] = b[1]
    mixed_required = any(int(a)!=b for a,b in nodes.items()) or any(int(a)!=b for a,b in ports.items())
    for a,b in mapping.items():
        if a[0] == "stage":
            mixed_required |= source.group["stage_ids"].index(a[1]) != target.group["stage_ids"].index(b[1])
        elif a[0] in ("operation","phase","flow"):
            mixed_required |= a[2:] != b[2:]
    return {"stage_map":stage_map,"operation_map":op_map,"phase_map":phase_map,"flow_map":flow_map,
            "node_map":nodes,"port_map":ports,"stages":stage_map,"operations":operation_ids,
            "hosts":nodes,"ports":ports,"verification_required":provisional,
            "mixed_verification_required":bool(mixed_required),
            "equivalence_status":"provisional" if provisional else "proven",
            "certificate_kind":"labelled_input_and_route_graph"}


def match_input_graphs(source,target,budget_seconds=3):
    # NetworkX temporarily changes the process recursion limit. Serialize that
    # scoped change across concurrent API planning and background execution.
    with _MATCH_LOCK:
        if budget_seconds <= 0: return None
        return _match_input_graphs(source,target,budget_seconds)
