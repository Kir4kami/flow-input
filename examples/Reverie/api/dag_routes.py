"""Collect exact routes from an already-built native simulator, without packets.

No Python ECMP/BFS reconstruction is used. A missing runtime or an unsuccessful
oracle produces an explicit unavailable certificate and keeps dedup conservative.
"""
from copy import deepcopy
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def flow_key(flow):
    return ",".join(str(flow[field]) for field in ("src", "dst", "sport", "dport"))


def _flows(plan):
    stages = plan["stages"]
    if isinstance(stages, dict):
        stages = stages.values()
    return {flow_key(flow): flow for stage in stages for operation in stage["operations"]
            for phase in operation["phases"] for flow in phase}


def _native_binary(project_root):
    project_root = Path(project_root)
    explicit = os.environ.get("FLOW_INPUT_SIM_BINARY")
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        return candidate.resolve() if candidate.is_file() and os.access(candidate, os.X_OK) else None
    directory = project_root / "build/examples/Reverie"
    # Read the launcher's configured target as data; never execute its lock file.
    lock = project_root / ".lock-ns3_linux_build"
    if lock.is_file():
        try:
            assignments = ast.parse(lock.read_text(encoding="utf-8")).body
            for assignment in assignments:
                if not isinstance(assignment, ast.Assign) or not any(
                        isinstance(target, ast.Name) and target.id == "ns3_runnable_programs"
                        for target in assignment.targets):
                    continue
                for value in ast.literal_eval(assignment.value):
                    candidate = directory / Path(value).name
                    if (re.fullmatch(r"ns[0-9.]+-sim(?:-[a-zA-Z0-9_]+)?", candidate.name)
                            and candidate.is_file() and os.access(candidate, os.X_OK)):
                        return candidate.resolve()
        except (OSError, SyntaxError, ValueError, TypeError):
            pass
    candidates = [path.resolve() for path in sorted(directory.glob("*-sim*"))
                  if re.fullmatch(r"ns[0-9.]+-sim(?:-[a-zA-Z0-9_]+)?", path.name)
                  and path.is_file() and os.access(path, os.X_OK)]
    plain = directory / "sim"
    if plain.is_file() and os.access(plain, os.X_OK):
        candidates.append(plain.resolve())
    # An arbitrary build profile cannot certify the runtime used by `ns3 run`.
    return candidates[0] if len(candidates) == 1 else None


def _runtime_fingerprint(binary, project_root):
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    libraries = {}
    seen = set()
    for path in sorted((project_root / "build/lib").glob("libns3*.so*")):
        actual = path.resolve()
        if actual in seen or not actual.is_file():
            continue
        seen.add(actual)
        libraries[actual.name] = hashlib.sha256(actual.read_bytes()).hexdigest()
    return {"native_binary_sha256": binary_hash, "native_library_sha256": libraries,
            "native_runtime_sha256": _digest({"binary": binary_hash, "libraries": libraries})}


def native_runtime_fingerprint(project_root):
    """Fingerprint the built ELF plus ns3 libraries; raise if unavailable."""
    project_root = Path(project_root).resolve()
    binary = _native_binary(project_root)
    if binary is None:
        raise FileNotFoundError("No already-built sim binary is available")
    return _runtime_fingerprint(binary, project_root)


def validate_native_routes(data, expected_flows, topology=None):
    """Reject partial, malformed or physically inconsistent native evidence."""
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("oracle") != "native" or data.get("certified") is not True):
        raise ValueError("Native route oracle did not return a certified v1 result")
    routes = data.get("routes")
    if not isinstance(routes, dict) or set(routes) != set(expected_flows):
        raise ValueError("Native route oracle flow population differs from the frozen plan")
    coverage = data.get("protocol_coverage", {})
    if coverage.get("data") != [17] or coverage.get("reverse") != [252, 253]:
        raise ValueError("Native route oracle does not cover RDMA data and ACK/NACK")
    physical = {}
    edges = None if topology is None else {
        frozenset((link["src"], link["dst"])) for link in topology["links"]}
    for key, flow in expected_flows.items():
        route = routes[key]
        if not isinstance(route, dict):
            raise ValueError("Invalid native route object")
        for direction, source, destination in (("forward", flow["src"], flow["dst"]),
                                                ("reverse", flow["dst"], flow["src"])):
            path = route.get(direction)
            hops = route.get(direction + "_hops")
            if (not isinstance(path, list) or len(path) < 2 or path[0] != source
                    or path[-1] != destination or len(set(path)) != len(path)
                    or not all(isinstance(node, int) and not isinstance(node, bool) and node >= 0 for node in path)
                    or not isinstance(hops, list) or len(hops) != len(path)-1):
                raise ValueError(f"Invalid {direction} native route for {key}")
            for index, hop in enumerate(hops):
                if not isinstance(hop, dict):
                    raise ValueError("Invalid native route hop")
                for field in ("node", "next_node", "out_if", "in_if"):
                    if not isinstance(hop.get(field), int) or isinstance(hop[field], bool) or hop[field] < 0:
                        raise ValueError("Invalid physical interface in native route")
                if hop["node"] != path[index] or hop["next_node"] != path[index+1]:
                    raise ValueError("Native route path and physical hops disagree")
                candidates = hop.get("next_hop_out_ifs")
                if (not isinstance(candidates, list) or not candidates
                        or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in candidates)
                        or hop["out_if"] not in candidates):
                    raise ValueError("Invalid ordered next-hop evidence in native route")
                if hop.get("hash_algorithm") not in ("ns3::Hash32", "SwitchNode::EcmpHash"):
                    raise ValueError("Unknown native route hash algorithm")
                if hop["hash_algorithm"] == "SwitchNode::EcmpHash" and (
                        not isinstance(hop.get("ecmp_seed"), int) or isinstance(hop["ecmp_seed"], bool)
                        or hop["ecmp_seed"] < 0):
                    raise ValueError("Missing native switch ECMP seed")
                if edges is not None and frozenset((path[index], path[index+1])) not in edges:
                    raise ValueError("Native route uses a link absent from the frozen topology")
                for interface, peer in (((hop["node"], hop["out_if"]), (hop["next_node"], hop["in_if"])),
                                        ((hop["next_node"], hop["in_if"]), (hop["node"], hop["out_if"]))):
                    if interface in physical and physical[interface] != peer:
                        raise ValueError("Native route assigns inconsistent physical interface peers")
                    physical[interface] = peer
    return data


def collect_plan_routes(plan, project_root, output_dir=None, *, timeout=30):
    """Return a new plan with native evidence or an explicit unavailable reason.

    The caller may persist output_dir for review. With no directory, all oracle
    inputs/logs live in a dedicated temporary directory and are removed afterward.
    Existing production topology, config, and traffic inputs are never changed.
    """
    result = deepcopy(plan)
    base = {"schema_version": 1, "oracle": "native", "certified": False,
            "experiment_fingerprint": plan.get("experiment_fingerprint"),
            "topology_fingerprint": _digest(plan["topology"]), "routes": {}}

    def unavailable(reason):
        result["route_certificate"] = dict(base, status="unavailable", reason=reason)
        return result

    if os.name != "posix":
        return unavailable("Native route oracle requires the built Linux runtime")
    project_root = Path(project_root).resolve()
    binary = _native_binary(project_root)
    if binary is None:
        return unavailable("No already-built sim binary is available; no build was attempted")
    if not plan.get("experiment_fingerprint"):
        return unavailable("The plan has no frozen experiment fingerprint")
    if not isinstance(plan.get("topology_text"), str) or not isinstance(plan.get("config_text"), str):
        return unavailable("The plan lacks frozen topology/config text snapshots")
    flows = _flows(plan)
    parent = None
    if output_dir is not None:
        parent = Path(output_dir).resolve() / "route_oracle"
        parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="native-routes-") if parent is None else None
    directory = Path(temporary.name if temporary else tempfile.mkdtemp(prefix="native-routes-", dir=parent))
    try:
        inputs = directory / "inputs"
        inputs.mkdir()
        topology = directory / "topology.txt"
        config = directory / "config-workload.txt"
        output = directory / "native_routes.json"
        topology.write_text(plan["topology_text"], encoding="utf-8")
        config.write_text(plan["config_text"], encoding="utf-8")
        lines = ["stat rdma operate:", "phase:0"]
        for flow in flows.values():
            lines.append("Type rdma_send src_node {src} src_port {sport} dst_node {dst} "
                         "dst_port {dport} priority {priority} msg_len {msg_len}".format(**flow))
        (inputs / "rdma_operate0.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
        (inputs / "dependence.txt").write_text("# oracle does not run packets\n", encoding="utf-8")
        command = [str(binary), f"--taskInputDir={inputs}", f"--topologyFile={topology}",
                   f"--conf={config}", f"--exportRoutesOnly={output}"]
        env = dict(os.environ, FLOW_INPUT_OUTPUT_DIR=str(directory), FLOW_INPUT_MIXED_GRANULARITY="0")
        libraries = str(project_root / "build/lib")
        env["LD_LIBRARY_PATH"] = libraries + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
        started = time.monotonic()
        process = subprocess.run(command, cwd=project_root, env=env, capture_output=True,
                                 text=True, timeout=timeout, check=False)
        (directory / "oracle.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            return unavailable(f"Native route oracle exited {process.returncode}: "
                               f"{(process.stdout+process.stderr)[-1600:]}")
        if not output.is_file():
            return unavailable("Native route oracle returned without native_routes.json")
        data = validate_native_routes(json.loads(output.read_text(encoding="utf-8")), flows, plan["topology"])
        fingerprint = _runtime_fingerprint(binary, project_root)
        certificate = dict(data, experiment_fingerprint=base["experiment_fingerprint"],
                           topology_fingerprint=base["topology_fingerprint"], status="available",
                           oracle_wall_time_seconds=time.monotonic()-started)
        certificate.update(fingerprint)
        if parent is not None:
            certificate["oracle_directory"] = str(directory)
        result["route_certificate"] = certificate
        if parent is not None:
            (directory / "certificate.json").write_text(json.dumps(certificate, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        return unavailable(f"Native route oracle unavailable: {type(error).__name__}: {error}")
    finally:
        if temporary is not None:
            temporary.cleanup()
