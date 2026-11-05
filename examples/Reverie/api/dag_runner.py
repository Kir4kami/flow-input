"""Execute frozen DAG plans, reuse proven representatives, and restore instances.

Every process owns an empty network and its input/output directory.  Neither
representative deduplication nor the worker pool removes a logical DAG vertex.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import threading
import time
from types import SimpleNamespace

try:
    from . import dag_plan
    from .dag_service import plan_projection
    from .simulation_monitor import SteadyStateMonitor
except ImportError:
    import dag_plan
    from simulation_monitor import SteadyStateMonitor

    def plan_projection(plan):
        # The API package normally supplies this projection. Keep direct-script
        # use working when only the api directory was put on sys.path.
        return {"counts": plan["counts"], "edges": plan["edges"], "groups": plan["groups"],
                "stages": [{"id": stage["id"], "type": stage.get("type", ""),
                    "predecessors": stage.get("predecessors", []),
                    "group_id": plan["stage_to_group"][stage["id"]],
                    "representative_id": plan["group_to_rep"][plan["stage_to_group"][stage["id"]]],
                    "operation_count": len(stage["operations"])} for stage in _stages(plan)],
                "representatives": [{key: rep[key] for key in ("id", "group_id", "member_group_ids")}
                                    for rep in _representatives(plan)],
                "stage_to_group": plan["stage_to_group"], "group_to_rep": plan["group_to_rep"],
                "input_fingerprint": plan.get("input_fingerprint")}


class DagExecutionError(RuntimeError):
    pass


class DagCancelled(DagExecutionError):
    pass


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _json_lines(path):
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                record = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise DagExecutionError(f"Malformed simulator telemetry in {path}: {exc}") from exc
            if not isinstance(record, dict):
                raise DagExecutionError(f"Invalid simulator telemetry object in {path}")
            records.append(record)
    return records


def terminate_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
    except ProcessLookupError:
        pass


def _stages(plan):
    values = plan["stages"]
    return values if isinstance(values, list) else list(values.values())


def _groups(plan):
    values = plan["groups"]
    return values if isinstance(values, list) else list(values.values())


def _stage_operations(stage):
    # Empty stages remain zero-time dependency barriers, including in a merged
    # full-DAG job where simply omitting them would disconnect their successors.
    return stage["operations"] or [{"id": stage["id"]+":empty", "index": 0,
                                    "phases": [[]], "predecessors": []}]


def _identity_mapping(plan, group):
    stages = {stage["id"]: stage for stage in _stages(plan)}
    return {
        "stage_map": {sid: sid for sid in group["stage_ids"]},
        "operation_map": {sid: {str(op.get("index", i)): op.get("index", i)
                                for i, op in enumerate(_stage_operations(stages[sid]))}
                          for sid in group["stage_ids"]},
        "phase_map": {sid: {str(op.get("index", i)): {str(p): p for p in range(len(op["phases"]))}
                           for i, op in enumerate(_stage_operations(stages[sid]))}
                      for sid in group["stage_ids"]},
        "flow_map": {sid: {str(op.get("index", i)): {str(p): {str(f): f for f in range(len(phase))}
                              for p, phase in enumerate(op["phases"])}
                          for i, op in enumerate(_stage_operations(stages[sid]))}
                     for sid in group["stage_ids"]},
        "node_map": {}, "port_map": {}, "verification_required": False,
        "mixed_verification_required": False, "proof_mode": plan.get("equivalence_mode", "packet"),
    }


def _representatives(plan):
    values = plan.get("representatives", [])
    return values if isinstance(values, list) else list(values.values())


def _mapping(rep, target_group, plan, representative_group):
    mapping = rep.get("mappings", {}).get(target_group)
    if mapping:
        return mapping
    if target_group == representative_group["id"]:
        return _identity_mapping(plan, representative_group)
    raise DagExecutionError(f"Missing equivalence mapping for {rep['id']} -> {target_group}")


def _integer(record, key):
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DagExecutionError(f"Invalid {key} in simulator telemetry: {value!r}")
    return int(value)


def _mapped(mapping, field, coordinates, default):
    value = mapping.get(field, {})
    for coordinate in coordinates:
        value = value.get(str(coordinate), value.get(coordinate, {})) if isinstance(value, dict) else {}
    return default if isinstance(value, dict) else value


def _provisional(plan):
    return any(rep.get("equivalence_status") == "provisional" or any(
        mapping.get("verification_required", False) for mapping in rep.get("mappings", {}).values())
        for rep in _representatives(plan))


def _mixed_witness_required(plan):
    return _provisional(plan) or any(rep.get("mixed_verification_required", False) or any(
        mapping.get("mixed_verification_required", False) for mapping in rep.get("mappings", {}).values())
        for rep in _representatives(plan))


def _representative_layout(result):
    return {tuple(sorted(rep["member_group_ids"])):
            {"source_group_id": rep["group_id"],
             "releases": result["representative_results"][rep["id"]].get("releases", {})}
            for rep in _representatives(result["plan"])}


def _deduplicate(plan, enabled=True, *, releases=None, allow_provisional=False, mode=None):
    return dag_plan.deduplicate_plan(plan, enabled=enabled, releases=releases,
                                     allow_provisional=allow_provisional, mode=mode)


def parse_job_result(job):
    """Validate precise telemetry, including all expected operation completions."""
    directory = Path(job["output_dir"])
    operation_events = _json_lines(directory / "operation_events.jsonl")
    flow_events = _json_lines(directory / "flow_events.jsonl")
    steady_events = _json_lines(directory / "steady_events.jsonl")
    starts, finishes = {}, {}
    for event in operation_events:
        kind = event.get("event")
        if kind not in ("operation_start", "operation_complete"):
            continue
        index = _integer(event, "operation_index")
        timestamp = _integer(event, "time_ns")
        if index not in job["operations"]:
            raise DagExecutionError(f"Unknown operation {index} in {directory}")
        if kind == "operation_start":
            starts.setdefault(index, timestamp)
        else:
            finishes[index] = timestamp
    expected = set(job["operations"])
    if set(starts) != expected or set(finishes) != expected:
        raise DagExecutionError(f"Incomplete operation telemetry in {directory}; "
                                f"missing starts={sorted(expected-set(starts))}, "
                                f"missing finishes={sorted(expected-set(finishes))}")
    for index in expected:
        if finishes[index] < starts[index]:
            raise DagExecutionError(f"Operation {index} finished before it started")
    flows = []
    used_flows = set()
    for record in flow_events:
        if record.get("event") != "flow_complete":
            continue
        event = dict(record)
        for key in ("operation_index", "phase_index", "src", "dst", "sport", "dport",
                    "priority", "size_bytes", "start_ns", "finish_ns", "fct_ns"):
            event[key] = _integer(event, key)
        if event["operation_index"] not in expected:
            raise DagExecutionError("Flow telemetry refers to an unknown operation")
        if event["finish_ns"] < event["start_ns"] or event["fct_ns"] != event["finish_ns"]-event["start_ns"]:
            raise DagExecutionError("Inconsistent flow completion timestamps")
        phases = job["operations"][event["operation_index"]]["phases"]
        if event["phase_index"] >= len(phases):
            raise DagExecutionError("Flow telemetry refers to an unknown phase")
        phase = phases[event["phase_index"]]
        identity = (event["src"], event["dst"], event["sport"], event["dport"],
                    event["priority"], event["size_bytes"])
        if "flow_index" not in event:
            candidates = [index for index, flow in enumerate(phase)
                          if tuple(flow[key] for key in ("src", "dst", "sport", "dport", "priority", "msg_len")) == identity]
            if not candidates:
                raise DagExecutionError("Simulator flow population differs from frozen input")
            if len(candidates) != 1:
                raise DagExecutionError("Precise flow_index is required for repeated identical flows")
            event["flow_index"] = candidates[0]
        flow_index = _integer(event, "flow_index")
        location = (event["operation_index"], event["phase_index"], flow_index)
        if flow_index >= len(phase) or location in used_flows:
            raise DagExecutionError("Duplicate or unknown flow_index in simulator telemetry")
        if tuple(phase[flow_index][key] for key in ("src", "dst", "sport", "dport", "priority", "msg_len")) != identity:
            raise DagExecutionError("Simulator flow population differs from frozen input at flow_index")
        used_flows.add(location)
        flows.append(event)
    expected_flows = sum(len(phase) for op in job["operations"].values() for phase in op["phases"])
    if len(flows) != expected_flows:
        raise DagExecutionError(f"Simulator completed {len(flows)} flows; expected {expected_flows} in {directory}")
    expected_population = Counter((index, phase_index, flow["src"], flow["dst"], flow["sport"],
                                   flow["dport"], flow["priority"], flow["msg_len"])
        for index, operation in job["operations"].items()
        for phase_index, phase in enumerate(operation["phases"]) for flow in phase)
    population = Counter(tuple(flow[key] for key in ("operation_index", "phase_index", "src", "dst",
                                                   "sport", "dport", "priority", "size_bytes"))
                         for flow in flows)
    if expected_population != population:
        raise DagExecutionError(f"Simulator flow population differs from frozen input in {directory}")
    windows = {}
    for index, operation in job["operations"].items():
        stage = operation["stage_id"]
        window = windows.setdefault(stage, {"start_ns": starts[index], "finish_ns": finishes[index]})
        window["start_ns"] = min(window["start_ns"], starts[index])
        window["finish_ns"] = max(window["finish_ns"], finishes[index])
    return {"job_id": job["task_id"], "representative_id": job["representative_id"],
            "input_group_id": job["group_id"], "mixed": job["mixed"], "releases": job["releases"],
            "stage_windows": windows, "operation_starts": starts, "operation_finishes": finishes,
            "flows": flows, "steady_events": steady_events,
            "duration_ns": max(finishes.values(), default=0),
            "wall_time_seconds": job.get("wall_time_seconds", 0),
            "output_dir": str(directory), "operation_count": len(expected),
            "execution_metadata": json.loads((directory / "execution_metadata.json").read_text(encoding="utf-8"))
                if (directory / "execution_metadata.json").exists() else {}}


def compare_results(reference, candidate, *, compare_steady=False):
    """Compare complete logical flow populations, not averages of representatives."""
    def index(result):
        population = {}
        for flow in result["flows"]:
            key = (flow["stage_id"], flow["operation_index"], flow["phase_index"], flow.get("flow_index"),
                   flow["src"], flow["dst"], flow["sport"], flow["dport"],
                   flow["priority"], flow["size_bytes"])
            population.setdefault(key, []).append(flow)
        for entries in population.values():
            entries.sort(key=lambda item: (item["start_ns"], item["finish_ns"], item["fct_ns"]))
        return population
    left, right = index(reference), index(candidate)
    missing = sum(len(left[key]) for key in left.keys()-right.keys())
    extra = sum(len(right[key]) for key in right.keys()-left.keys())
    differences = []
    maximum_fct = maximum_start = maximum_finish = 0
    mismatched = 0
    for key in left.keys() & right.keys():
        a, b = left[key], right[key]
        missing += max(0, len(a)-len(b)); extra += max(0, len(b)-len(a))
        for expected, actual in zip(a, b):
            fct = actual["fct_ns"]-expected["fct_ns"]
            start = actual["start_ns"]-expected["start_ns"]
            finish = actual["finish_ns"]-expected["finish_ns"]
            maximum_fct = max(maximum_fct, abs(fct))
            maximum_start = max(maximum_start, abs(start))
            maximum_finish = max(maximum_finish, abs(finish))
            if fct or start or finish:
                mismatched += 1
                if len(differences) < 20:
                    differences.append({"stage_id": key[0], "operation_index": key[1],
                                        "phase_index": key[2], "fct_delta_ns": fct,
                                        "start_delta_ns": start, "finish_delta_ns": finish})
    makespan = candidate["summary"]["makespan_ns"]-reference["summary"]["makespan_ns"]
    reference_stages = {stage["id"]: stage for stage in reference.get("schedule", [])}
    candidate_stages = {stage["id"]: stage for stage in candidate.get("schedule", [])}
    missing_stages = sorted(reference_stages.keys()-candidate_stages.keys())
    extra_stages = sorted(candidate_stages.keys()-reference_stages.keys())
    stage_differences = []
    for stage_id in reference_stages.keys() & candidate_stages.keys():
        expected, actual = reference_stages[stage_id], candidate_stages[stage_id]
        delta = {key+"_delta_ns": actual[key]-expected[key]
                 for key in ("start_ns", "finish_ns", "duration_ns")}
        if any(delta.values()):
            stage_differences.append({"stage_id": stage_id, **delta})
    def operation_index(result):
        return {(op["stage_id"], op["operation_index"]): op for op in result.get("operations", [])}
    left_ops, right_ops = operation_index(reference), operation_index(candidate)
    missing_ops = sorted(left_ops.keys()-right_ops.keys()); extra_ops = sorted(right_ops.keys()-left_ops.keys())
    operation_differences = []
    for key in left_ops.keys() & right_ops.keys():
        delta = {field+"_delta_ns": right_ops[key][field]-left_ops[key][field]
                 for field in ("start_ns", "finish_ns", "duration_ns")}
        if any(delta.values()):
            operation_differences.append({"stage_id": key[0], "operation_index": key[1], **delta})
    steady_differences = []
    if compare_steady:
        def events(result):
            by_group = {}
            for event in result.get("steady_state_timeline", []):
                by_group.setdefault(event["group_id"], []).append((event["event"], event["local_sim_time_ns"]))
            return by_group  # Same-timestamp enter/exit order changes the state.
        left_events, right_events = events(reference), events(candidate)
        left_execution, right_execution = reference.get("group_execution", {}), candidate.get("group_execution", {})
        for gid in sorted(set(left_events) | set(right_events) | set(left_execution) | set(right_execution)):
            a = left_execution.get(gid, {}).get("execution_metadata", {})
            b = right_execution.get(gid, {}).get("execution_metadata", {})
            if left_events.get(gid, []) != right_events.get(gid, []) or a.get("transition_count") != b.get("transition_count"):
                steady_differences.append({"group_id": gid, "reference_events": left_events.get(gid, []),
                    "candidate_events": right_events.get(gid, []), "reference_transitions": a.get("transition_count"),
                    "candidate_transitions": b.get("transition_count")})
    return {"passed": not (missing or extra or mismatched or makespan or missing_stages
                            or extra_stages or stage_differences or missing_ops or extra_ops
                            or operation_differences or steady_differences),
            "missing_flows": missing, "extra_flows": extra,
            "mismatched_flows": mismatched, "max_fct_error_ns": maximum_fct,
            "max_start_error_ns": maximum_start, "max_finish_error_ns": maximum_finish,
            "makespan_delta_ns": makespan, "examples": differences,
            "missing_stages": missing_stages, "extra_stages": extra_stages,
            "mismatched_stages": len(stage_differences), "stage_examples": stage_differences[:20],
            "missing_operations": missing_ops, "extra_operations": extra_ops,
            "mismatched_operations": len(operation_differences), "operation_examples": operation_differences[:20],
            "steady_compared": compare_steady, "mismatched_steady_groups": len(steady_differences),
            "steady_examples": steady_differences[:20]}


class _Runner:
    def __init__(self, plan, project_root, run_dir, *, workers, monitor, state,
                 job_timeout, job_executor, simulation_id):
        self.plan = deepcopy(plan)
        self.project_root = Path(project_root).resolve()
        self.run_dir = Path(run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.workers = max(1, min(int(workers), 32))
        self.monitor = monitor or SteadyStateMonitor()
        self.state = state or SimpleNamespace(cancelled=False, lock=threading.RLock(), processes=set())
        if not hasattr(self.state, "processes"):
            self.state.processes = set()
        self.job_timeout = float(job_timeout)
        self.job_executor = job_executor
        self.simulation_id = simulation_id or self.run_dir.name
        self.abort = threading.Event()
        self.lock = threading.RLock()
        self.next_job = 1
        self.jobs = []
        self.cache = {}
        self.binary_fingerprint = None
        self.started = time.monotonic()
        self.execution = {"phase": "planning", "logical_unit_count": len(_stages(plan)),
                          "group_count": len(_groups(plan)),
                          "representative_count": len(_representatives(plan)),
                          "reused_unit_count": plan.get("counts", {}).get("reused_unit_count", 0),
                          "job_count": 0, "completed_jobs": 0, "round": 0}
        self.state.execution = self.execution
        self.monitor.reset(self.run_dir, 0, self.simulation_id)
        self._snapshot()

    def _snapshot(self):
        source = self.plan.get("topology_file") or self.plan.get("topology_path")
        if not source:
            source = self.project_root / "examples/Reverie/leaf-spine.txt"
        self.topology = self.run_dir / "inputs/topology.txt"
        self.topology.parent.mkdir(parents=True, exist_ok=True)
        self.topology.write_text(self.plan.get("topology_text") or Path(source).read_text(encoding="utf-8"),
                                 encoding="utf-8")
        source = self.plan.get("config_file") or self.project_root / "examples/Reverie/config-workload.txt"
        text = self.plan.get("config_text")
        if text is None:
            text = Path(source).read_text(encoding="utf-8") if Path(source).exists() else ""
        text = re.sub(r"(?m)^TOPOLOGY_FILE\s+.*$", lambda _: "TOPOLOGY_FILE " + str(self.topology), text)
        self.config = self.run_dir / "inputs/config-workload.txt"
        self.config.write_text(text, encoding="utf-8")
        # The parsed phase/flow data in the manifest are the immutable input
        # snapshot; no job reads mutable generated task directories.
        _write_json(self.run_dir / "input_plan.json", self.plan)
        self.manifest = {"schema_version": 1, "simulation_id": self.simulation_id,
                         "input_fingerprint": self.plan.get("input_fingerprint"),
                         "experiment_fingerprint": self.plan.get("experiment_fingerprint"),
                         "worker_count": self.workers, "topology_file": str(self.topology),
                         "config_file": str(self.config), "jobs": []}
        _write_json(self.run_dir / "manifest.json", self.manifest)

    def check(self):
        if self.state.cancelled or self.abort.is_set():
            raise DagCancelled("DAG simulation cancelled")

    def progress(self, **updates):
        with self.lock:
            self.execution.update(updates)
            self.state.execution = dict(self.execution)
            self.monitor.execution_summary = dict(self.execution)

    def command(self, command, directory, env=None):
        self.check()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "evaluation.out").open("w", encoding="utf-8") as log:
            with self.state.lock:
                self.check()
                process = subprocess.Popen(command, cwd=self.project_root, env=env,
                                           stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=(os.name == "posix"))
                self.state.processes.add(process)
            deadline = time.monotonic()+self.job_timeout
            try:
                while process.poll() is None:
                    self.check()
                    if time.monotonic() > deadline:
                        raise DagExecutionError(f"Simulation exceeded {self.job_timeout:g} seconds")
                    time.sleep(.025)
                if process.returncode:
                    tail = (directory / "evaluation.out").read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise DagExecutionError(f"Simulator exited with code {process.returncode}: {tail}")
            finally:
                terminate_process(process)
                with self.state.lock:
                    self.state.processes.discard(process)

    def build(self):
        self.progress(phase="building")
        self.command([str(self.project_root / "ns3"), "build", "sim", "-j", str(self.workers)],
                     self.run_dir / "build")

    def fingerprint(self):
        if self.binary_fingerprint is None:
            runtime = None
            if not self.job_executor:
                try:
                    from .dag_routes import native_runtime_fingerprint
                except ImportError:
                    from dag_routes import native_runtime_fingerprint
                try:
                    runtime = native_runtime_fingerprint(self.project_root)
                except (FileNotFoundError, OSError) as exc:
                    raise DagExecutionError(f"Cannot fingerprint the native simulation runtime: {exc}") from exc
            directory = self.project_root / "build/examples/Reverie"
            binaries = ([Path(os.environ["FLOW_INPUT_SIM_BINARY"])] if os.environ.get("FLOW_INPUT_SIM_BINARY")
                        else sorted(directory.glob("*-sim-*")) + [directory / "sim"])
            binary = next((path for path in binaries if path.is_file() and os.access(path, os.X_OK)), None)
            self.native_binary_sha256 = (runtime["native_binary_sha256"] if runtime else
                                         hashlib.sha256(binary.read_bytes()).hexdigest() if binary else "test-executor")
            self.binary_fingerprint = runtime["native_runtime_sha256"] if runtime else self.native_binary_sha256
            self.manifest["simulator_fingerprint"] = self.binary_fingerprint
            _write_json(self.run_dir / "manifest.json", self.manifest)
        return self.binary_fingerprint

    def verify_routes(self, job, plan):
        certificate = plan.get("route_certificate", {})
        if certificate.get("certified") is not True:
            return {"performed": False}
        if (not self.job_executor and certificate.get("native_binary_sha256")
                and (self.fingerprint() and certificate["native_binary_sha256"] != self.native_binary_sha256)):
            raise DagExecutionError("Native route certificate belongs to a different simulator binary")
        if (not self.job_executor and certificate.get("native_runtime_sha256")
                and certificate["native_runtime_sha256"] != self.fingerprint()):
            raise DagExecutionError("Native route certificate belongs to different simulator libraries")
        path = Path(job["output_dir"]) / "native_routes.json"
        if not path.exists():
            raise DagExecutionError("Certified routes require per-job native_routes.json evidence")
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = {",".join(str(flow[field]) for field in ("src", "dst", "sport", "dport"))
                for operation in job["operations"].values() for phase in operation["phases"] for flow in phase}
        actual = data.get("routes", {})
        if data.get("certified") is not True or set(actual) != keys:
            raise DagExecutionError("Actual native route population differs from this job's frozen flows")
        expected = certificate.get("routes", {})
        for key in keys:
            if key not in expected or any(actual[key].get(field) != expected[key].get(field)
                    for field in ("forward", "reverse", "forward_hops", "reverse_hops")):
                raise DagExecutionError(f"Actual native route differs from the frozen certificate for {key}")
        return {"performed": True, "passed": True, "route_count": len(keys),
                "native_binary_sha256": certificate.get("native_binary_sha256")}

    def evidence_context(self, plan, mixed):
        fingerprint = self.fingerprint()
        return {"input_fingerprint": plan.get("input_fingerprint"),
                "experiment_fingerprint": plan.get("experiment_fingerprint"),
                "simulator_fingerprint": fingerprint, "native_binary_sha256": self.native_binary_sha256,
                "native_runtime_sha256": fingerprint,
                "boundary_releases": plan.get("runtime_boundary_releases", plan.get("boundary_releases", {})),
                "mode": "mixed" if mixed else "packet"}

    def _job(self, plan, group, rep_id, releases, mode, role):
        stage_by_id = {stage["id"]: stage for stage in _stages(plan)}
        with self.lock:
            task_id = self.next_job; self.next_job += 1
        directory = self.run_dir / f"task{task_id}"
        inputs = directory / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        operations = {}; by_stage = {}
        for stage_id in group["stage_ids"]:
            by_stage[stage_id] = []
            for local_index, operation in enumerate(_stage_operations(stage_by_id[stage_id])):
                index = len(operations)
                operations[index] = {**deepcopy(operation), "stage_id": stage_id,
                                     "local_index": operation.get("index", local_index)}
                by_stage[stage_id].append(index)
        by_id = {operation["id"]: index for index, operation in operations.items()}
        dependencies = set()
        for index, operation in operations.items():
            for predecessor in operation.get("predecessors", []):
                if predecessor in by_id:
                    dependencies.add((index, by_id[predecessor]))
            stage = stage_by_id[operation["stage_id"]]
            for parent in stage.get("predecessors", []):
                for parent_op in by_stage.get(parent, []):
                    dependencies.add((index, parent_op))
            lines = ["stat rdma operate:"]
            for phase_index, phase in enumerate(operation["phases"]):
                lines.append(f"phase:{phase_index}")
                for flow in phase:
                    lines.append("Type rdma_send src_node {src} src_port {sport} dst_node {dst} "
                                 "dst_port {dport} priority {priority} msg_len {msg_len}".format(**flow))
            (inputs / f"rdma_operate{index}.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
        (inputs / "dependence.txt").write_text("".join(f"{child}:{parent}\n" for child, parent in sorted(dependencies))
                                                   or "# no dependencies\n", encoding="utf-8")
        (inputs / "release_times.txt").write_text("".join(
            f"{index} {int(releases.get(operation['stage_id'], 0))}\n"
            for index, operation in operations.items()), encoding="utf-8")
        job = {"task_id": task_id, "representative_id": rep_id, "group_id": group["id"],
               "stage_ids": list(group["stage_ids"]), "operations": operations,
               "output_dir": str(directory), "input_dir": str(inputs),
               "releases": releases, "mixed": mode, "run_role": role,
               "evidence_context": self.evidence_context(plan, mode),
               "route_certificate": plan.get("route_certificate", {})}
        _write_json(directory / "job.json", {key: value for key, value in job.items() if key != "route_certificate"})
        self.monitor.register_task(task_id, {"representative_id": rep_id,
                                            "group_id": group["id"],
                                            "unit_ids": group["stage_ids"], "run_role": role})
        with self.lock:
            self.jobs.append(job)
            self.manifest["jobs"].append({key: deepcopy(job[key]) for key in
                ("task_id", "representative_id", "group_id", "stage_ids", "input_dir",
                 "output_dir", "releases", "mixed", "run_role")})
            _write_json(self.run_dir / "manifest.json", self.manifest)
            self.progress(job_count=len(self.jobs))
        return job

    def execute(self, job, calibration=None):
        self.check()
        directory = Path(job["output_dir"])
        if calibration:
            source = Path(calibration["output_dir"]) / "flow_SwitchStats.txt"
            if source.exists():
                (directory / "flow_SwitchStats.txt").write_bytes(source.read_bytes())
        started = time.monotonic()
        code = 1
        try:
            if self.job_executor:
                self.job_executor(job)
            else:
                env = dict(os.environ, FLOW_INPUT_OUTPUT_DIR=str(directory),
                           FLOW_INPUT_TASK_ID=str(job["task_id"]),
                           FLOW_INPUT_MIXED_GRANULARITY="1" if job["mixed"] else "0")
                args = ("sim --TASKINDEX={task} --taskInputDir={inputs} --topologyFile={topology} "
                        "--conf={config} --START_TIME=0 --END_TIME=864000 "
                        "--FLOW_LAUNCH_END_TIME=3600 --fctOutFile=evaluation.fct "
                        "--torOutFile=evaluation.tor --pfcOutFile=evaluation.pfc").format(
                            task=job["task_id"], inputs=shlex.quote(job["input_dir"]),
                            topology=shlex.quote(str(self.topology)), config=shlex.quote(str(self.config)))
                self.command([str(self.project_root / "ns3"), "run", "--no-build", args], directory, env)
            job["wall_time_seconds"] = time.monotonic()-started
            result = parse_job_result(job)
            result["route_verification"] = self.verify_routes(job, {"route_certificate": job["route_certificate"]})
            result["evidence_context"] = job["evidence_context"]
            code = 0
            _write_json(directory / "result.json", result)
            return result
        finally:
            (directory / "exit_code").write_text(str(code)+"\n", encoding="utf-8")
            with self.lock:
                entry = next(item for item in self.manifest["jobs"] if item["task_id"] == job["task_id"])
                entry.update(exit_code=code, wall_time_seconds=time.monotonic()-started)
                _write_json(self.run_dir / "manifest.json", self.manifest)
                self.progress(completed_jobs=self.execution["completed_jobs"]+1)

    def key(self, plan, group, releases, mixed):
        stages = {stage["id"]: stage for stage in _stages(plan)}
        data = {"stages": [stages[sid] for sid in group["stage_ids"]],
                "releases": releases, "mixed": mixed,
                "experiment": plan.get("experiment_fingerprint"), "simulator": self.fingerprint()}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def _run_jobs(self, requests):
        results = {}
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="dag-sim") as pool:
            futures = {pool.submit(self.execute, job, calibration): key for key, job, calibration in requests}
            try:
                for future in as_completed(futures):
                    self.check()
                    results[futures[future]] = future.result()
            except BaseException:
                self.abort.set()
                with self.state.lock:
                    for process in list(self.state.processes):
                        terminate_process(process)
                for future in futures:
                    future.cancel()
                raise
        return results

    def run_plan(self, plan, *, mixed=False, role="representative", use_cache=True,
                 allow_provisional=False, restrict_to_plan=False):
        phase_started = time.monotonic()
        stages = {stage["id"]: stage for stage in _stages(plan)}
        groups = {group["id"]: group for group in _groups(plan)}
        representatives = _representatives(plan)
        reps = {rep["id"]: rep for rep in representatives}
        group_rep = {gid: rep["id"] for rep in representatives for gid in rep["member_group_ids"]}
        if set(group_rep) != set(groups):
            raise DagExecutionError("The representative mapping does not cover every group")
        self.progress(phase=role, group_count=len(groups), representative_count=len(reps),
                      reused_unit_count=plan.get("counts", {}).get("reused_unit_count", len(groups)-len(reps)),
                      representatives=[{"id": rep["id"], "group_ids": rep["member_group_ids"],
                                        "unit_ids": [sid for gid in rep["member_group_ids"] for sid in groups[gid]["stage_ids"]]}
                                       for rep in representatives])
        rep_results = {}; variants = {}; group_bindings = {}; group_results = {}; stage_results = {}
        known_releases = {}; singleton_requests = []; request_keys = {}

        def allocate_id(preferred):
            identifier = preferred
            while identifier in variants:
                identifier += "_"
            return identifier

        def prepare(group, identifier, releases):
            key = self.key(plan, group, releases, mixed)
            if use_cache and key in self.cache:
                rep_results[identifier] = {**self.cache[key], "representative_id": identifier}
                return None
            calibration = self.cache.get(self.key(plan, group, releases, False)) if mixed else None
            if mixed and calibration is None:
                cal_job = self._job(plan, group, identifier, releases, False, "calibration")
                calibration = self.execute(cal_job)
                self.cache[self.key(plan, group, releases, False)] = calibration
            job = self._job(plan, group, identifier, releases, mixed, role)
            request_keys[identifier] = key
            return identifier, job, calibration

        def run_requests(requests):
            executed = self._run_jobs(requests)
            rep_results.update(executed)
            if use_cache:
                for identifier, result in executed.items():
                    self.cache[request_keys[identifier]] = result

        # A one-stage representative has one boundary and starts at local zero;
        # all such representatives are independent jobs even if their logical
        # occurrences lie on different levels of the original DAG.
        for rep in representatives:
            group = groups[rep["group_id"]]
            if len(group["stage_ids"]) != 1:
                continue
            releases = {group["stage_ids"][0]: 0}
            variants[rep["id"]] = deepcopy(rep)
            variants[rep["id"]]["boundary_releases"] = releases
            for gid in rep["member_group_ids"]:
                group_bindings[gid] = (rep["id"], _mapping(rep, gid, plan, group))
            request = prepare(group, rep["id"], releases)
            if request: singleton_requests.append(request)
        run_requests(singleton_requests)
        pending = set(groups)
        while pending:
            ready = [gid for gid in groups if gid in pending and
                     all(parent in group_results for parent in groups[gid].get("predecessors", []))]
            if not ready:
                raise DagExecutionError("Group dependency graph contains a cycle or missing predecessor")
            requests = []; origins = {}
            for gid in ready:
                group = groups[gid]; rep_id = group_rep[gid]; rep = reps[rep_id]
                external = {sid: max((stage_results[parent]["finish_ns"]
                                     for parent in stages[sid].get("predecessors", [])
                                     if parent not in group["stage_ids"]), default=0)
                            for sid in group["stage_ids"]}
                entry = [sid for sid in group["stage_ids"]
                         if not any(parent in group["stage_ids"] for parent in stages[sid].get("predecessors", []))]
                origin = min((external[sid] for sid in entry), default=0)
                origins[gid] = origin
                if len(group["stage_ids"]) == 1:
                    continue
                releases = {sid: max(0, timestamp-origin) for sid, timestamp in external.items()}
                known_releases.update(releases)
                match = None
                matcher = getattr(dag_plan, "match_groups", None)
                if plan.get("deduplicate_enabled", True) and matcher:
                    for identifier, variant in variants.items():
                        source = groups[variant["group_id"]]
                        if len(source["stage_ids"]) <= 1: continue
                        if restrict_to_plan and group_rep[source["id"]] != group_rep[gid]: continue
                        profile = {**variant["boundary_releases"], **releases}
                        mapping = matcher(plan, source, group, releases=profile,
                                          allow_provisional=allow_provisional, mode="mixed" if mixed else "packet")
                        if mapping is not None:
                            match = (identifier, mapping)
                            break
                if match is None:
                    identifier = allocate_id(rep_id)
                    identity = _identity_mapping(plan, group)
                    variants[identifier] = {"id": identifier, "group_id": gid,
                        "member_group_ids": [gid], "mappings": {gid: identity},
                        "boundary_releases": releases, "equivalence_status": "proven"}
                    group_bindings[gid] = (identifier, identity)
                    request = prepare(group, identifier, releases)
                    if request: requests.append(request)
                else:
                    identifier, mapping = match
                    variants[identifier]["member_group_ids"].append(gid)
                    variants[identifier]["mappings"][gid] = mapping
                    if (mapping.get("verification_required") or mapping.get("equivalence_status") == "provisional"
                            or (mixed and mapping.get("mixed_verification_required"))):
                        variants[identifier]["equivalence_status"] = "provisional"
                    if mapping.get("verification_required"):
                        variants[identifier]["verification_required"] = True
                    if mapping.get("mixed_verification_required"):
                        variants[identifier]["mixed_verification_required"] = True
                    group_bindings[gid] = (identifier, mapping)
            run_requests(requests)
            for gid in ready:
                group = groups[gid]
                rep_id, mapping = group_bindings[gid]
                local = rep_results[rep_id]
                rep_group = groups[variants[rep_id]["group_id"]]
                expanded = self.expand(plan, rep_group, group, local, origins[gid], mapping)
                group_results[gid] = expanded
                stage_results.update({stage["id"]: stage for stage in expanded["schedule"]})
                pending.remove(gid)
        schedule = [stage_results[stage["id"]] for stage in _stages(plan)]
        flows = [flow for gid in groups for flow in group_results[gid]["flows"]]
        operations = [operation for gid in groups for operation in group_results[gid]["operations"]]
        steady = [event for gid in groups for event in group_results[gid]["steady_state_timeline"]]
        effective_plan = deepcopy(plan)
        effective_plan["representatives"] = list(variants.values())
        for variant in effective_plan["representatives"]:
            required = False
            for mapping in variant.get("mappings", {}).values():
                mapping["proof_mode"] = "mixed" if mixed else "packet"
                needs_validation = bool(mapping.get("mixed_verification_required") if mixed
                                        else mapping.get("verification_required"))
                mapping["equivalence_status"] = "provisional" if needs_validation else "proven"
                required |= needs_validation
            variant["equivalence_status"] = "provisional" if required else "proven"
        effective_plan["group_to_rep"] = {gid: identifier for gid, (identifier, _) in group_bindings.items()}
        reused_units = sum(len(groups[gid]["stage_ids"]) for variant in variants.values()
                           for gid in variant["member_group_ids"] if gid != variant["group_id"])
        effective_plan["counts"] = {"logical_unit_count": len(stages), "group_count": len(groups),
            "representative_count": len(variants), "reused_unit_count": reused_units,
            "reused_group_count": len(groups)-len(variants)}
        effective_plan["runtime_boundary_releases"] = known_releases
        effective_plan["equivalence_mode"] = "mixed" if mixed else "packet"
        effective_plan["equivalence_context"] = self.evidence_context(effective_plan, mixed)
        provisional_members = sum(bool(mapping.get("verification_required") or
            (mixed and mapping.get("mixed_verification_required")))
            for variant in variants.values() for mapping in variant.get("mappings", {}).values())
        effective_plan.setdefault("deduplication", {}).update(
            provisional_member_group_count=provisional_members, requires_mode_validation=bool(provisional_members))
        group_execution = {gid: {"representative_id": group_bindings[gid][0],
            "job_id": rep_results[group_bindings[gid][0]]["job_id"],
            "source_group_id": variants[group_bindings[gid][0]]["group_id"],
            "execution_metadata": rep_results[group_bindings[gid][0]].get("execution_metadata", {})}
            for gid in groups}
        summary = {"logical_unit_count": len(stages), "group_count": len(groups),
                   "representative_count": len(variants), "reused_unit_count": reused_units,
                   "makespan_ns": max((stage["finish_ns"] for stage in schedule), default=0),
                   "total_flows": len(flows), "total_bytes": sum(flow["size_bytes"] for flow in flows),
                   "wall_time_seconds": time.monotonic()-phase_started,
                   "steady_entry_count": sum(event.get("event") == "enter" for event in steady),
                   "mixed_granularity": mixed,
                   "simulation_wall_time_ns": sum(local.get("execution_metadata", {}).get("simulation_wall_time_ns", 0)
                                                  for local in rep_results.values()),
                   "representative_process_wall_time_seconds": sum(local.get("wall_time_seconds", 0)
                                                                    for local in rep_results.values())}
        self.progress(**effective_plan["counts"], representatives=[{key: variant[key] for key in
                      ("id", "group_id", "member_group_ids")} for variant in variants.values()])
        return {"summary": summary, "schedule": schedule, "flows": flows, "operations": operations,
                "steady_state_timeline": sorted(steady, key=lambda e: (e["global_sim_time_ns"], e["group_id"])),
                "representative_results": rep_results, "group_execution": group_execution, "plan": effective_plan}

    def expand(self, plan, representative_group, target_group, local, origin, mapping):
        stages = {stage["id"]: stage for stage in _stages(plan)}
        stage_map = mapping.get("stage_map", mapping.get("stages", {}))
        hosts = mapping.get("node_map", mapping.get("hosts", {}))
        ports = mapping.get("port_map", mapping.get("ports", {}))
        operation_info = {}
        index = 0
        for sid in representative_group["stage_ids"]:
            for i, operation in enumerate(_stage_operations(stages[sid])):
                operation_info[index] = (sid, operation.get("index", i)); index += 1
        reused = target_group["id"] != representative_group["id"]
        schedule = []
        for source_stage in representative_group["stage_ids"]:
            target_stage = stage_map[source_stage]
            window = local["stage_windows"][source_stage]
            schedule.append({"id": target_stage, "group_id": target_group["id"],
                             "representative_id": local["representative_id"],
                             "job_id": local["job_id"], "reused": reused,
                             "start_ns": int(origin+window["start_ns"]),
                             "finish_ns": int(origin+window["finish_ns"]),
                             "duration_ns": int(window["finish_ns"]-window["start_ns"])})
        flows = []
        operations = []
        for index, (source_stage, source_op) in operation_info.items():
            start = local["operation_starts"][index]; finish = local["operation_finishes"][index]
            operations.append({"stage_id": stage_map[source_stage],
                "operation_index": int(_mapped(mapping, "operation_map", (source_stage, source_op), source_op)),
                "start_ns": int(origin+start), "finish_ns": int(origin+finish), "duration_ns": finish-start,
                "representative_id": local["representative_id"], "job_id": local["job_id"],
                "source_group_id": representative_group["id"], "reused": reused})
        for record in local["flows"]:
            source_stage, source_op = operation_info[record["operation_index"]]
            target_stage = stage_map[source_stage]
            target_op = _mapped(mapping, "operation_map", (source_stage, source_op), source_op)
            phase_index = record["phase_index"]
            target_phase = _mapped(mapping, "phase_map", (source_stage, source_op, phase_index), phase_index)
            target_flow = _mapped(mapping, "flow_map", (source_stage, source_op, phase_index, record["flow_index"]), record["flow_index"])
            event = dict(record, stage_id=target_stage, operation_index=int(target_op),
                         phase_index=int(target_phase), flow_index=int(target_flow),
                         representative_id=local["representative_id"], job_id=local["job_id"],
                         reused=reused, group_id=target_group["id"],
                         source_group_id=representative_group["id"], mode="mixed" if local.get("mixed") else "packet",
                         source_stage_id=source_stage, source_operation_index=source_op,
                         source_phase_index=phase_index, source_flow_index=record["flow_index"],
                         start_ns=int(origin+record["start_ns"]), finish_ns=int(origin+record["finish_ns"]))
            for key in ("src", "dst"):
                event[key] = int(hosts.get(str(record[key]), hosts.get(record[key], record[key])))
            for key in ("sport", "dport"):
                event[key] = int(ports.get(str(record[key]), ports.get(record[key], record[key])))
            flows.append(event)
        steady = []
        for record in local["steady_events"]:
            steady.append({**record, "group_id": target_group["id"],
                           "stage_ids": target_group["stage_ids"],
                           "representative_id": local["representative_id"], "actual_job_id": local["job_id"],
                           "local_sim_time_ns": record["sim_time_ns"],
                           "global_sim_time_ns": int(origin+record["sim_time_ns"]),
                           "source": "reused" if reused else "simulator",
                           "actual_wall_clock_ts": record.get("wall_clock_ts"),
                           "wall_clock_ts": None if reused else record.get("wall_clock_ts")})
        return {"schedule": schedule, "flows": flows, "operations": operations, "steady_state_timeline": steady}


def run_dag_simulation(plan, project_root, run_dir, *, mixed=False, workers=2,
                       monitor=None, state=None, validate=False, deduplicate=True,
                       build=True, job_timeout=3600, simulation_id=None,
                       job_executor=None, verify_dedup=None):
    """Run and validate a complete logical DAG, preserving representative provenance.

    ``job_executor`` is a test seam: production always launches the real ns-3
    executable. It must write the same precise JSONL telemetry as the simulator.
    ``verify_dedup`` checks provisional reuse without launching the complete
    DAG baseline. Its default preserves the previous ``validate`` behavior.
    """
    verify_dedup = bool(validate) if verify_dedup is None else bool(verify_dedup)
    packet_candidates = bool(verify_dedup and deduplicate)
    mixed_candidates = packet_candidates
    plan = _deduplicate(deepcopy(plan), enabled=False, mode="packet")
    runner = _Runner(plan, project_root, run_dir, workers=workers, monitor=monitor,
                     state=state, job_timeout=job_timeout, job_executor=job_executor,
                     simulation_id=simulation_id)
    try:
        if build:
            runner.build()
        if job_executor is None:
            try:
                from .dag_routes import collect_plan_routes
            except ImportError:
                from dag_routes import collect_plan_routes
            runner.progress(phase="certifying_routes")
            runner.check()
            plan = collect_plan_routes(plan, project_root, output_dir=run_dir)
            runner.check()
        plan = _deduplicate(plan, enabled=deduplicate, allow_provisional=packet_candidates, mode="packet")
        runner.plan = deepcopy(plan)
        _write_json(runner.run_dir / "input_plan.json", plan)
        runner.manifest["input_fingerprint"] = plan.get("input_fingerprint")
        runner.manifest["route_certificate_status"] = plan.get("route_certificate", {}).get("status")
        _write_json(runner.run_dir / "manifest.json", runner.manifest)
        rounds = []; whole = None
        validation = {"performed": bool(validate), "passed": None}
        mixed_comparison = {"performed": False}
        deduplication_validation = {mode: {"performed": False, "passed": None, "fallback": False,
                                          "reason": None} for mode in ("packet", "mixed")}

        def refine(current, conflicts, allow_provisional):
            updated = dag_plan.refine_groups(current, conflicts)
            if len(_groups(updated)) >= len(_groups(current)):
                raise DagExecutionError("Conflict refinement did not reduce the partition")
            return _deduplicate(updated, enabled=deduplicate, allow_provisional=allow_provisional, mode="packet")

        def record_mode(mode, output, performed, passed, evidence_file=None):
            report = deduplication_validation[mode]
            count = output["summary"]["representative_count"]
            report.setdefault("candidate_representative_count", count)
            report.update(performed=performed, passed=passed, final_representative_count=count,
                          strict_representative_count=_deduplicate(output["plan"], enabled=deduplicate,
                            releases=output["plan"].get("runtime_boundary_releases"),
                            allow_provisional=False, mode=mode)["counts"]["representative_count"],
                          provisional=_provisional(output["plan"]),
                          mixed_verification_required=_mixed_witness_required(output["plan"]) if mode == "mixed" else False,
                          evidence_context=runner.evidence_context(output["plan"], mode == "mixed"))
            if evidence_file: report["evidence_file"] = evidence_file

        def save_candidate_failure(mode, output, witness, comparisons):
            filename = f"dedup_{mode}_candidate_failure.json"
            _write_json(runner.run_dir / filename, {"candidate": output, "witness": witness,
                "comparisons": comparisons, "evidence_context": runner.evidence_context(output["plan"], mode == "mixed")})
            report = deduplication_validation[mode]
            report.update(performed=True, passed=False, fallback=True,
                candidate_representative_count=output["summary"]["representative_count"],
                reason="Independent same-mode witness disagreed; reran using proven equivalence only",
                candidate_evidence_file=filename, candidate_comparisons=comparisons)

        # Each unsuccessful pass merges at least two groups. The bounded loop
        # also covers new overlap caused by an accelerated schedule changing a
        # predecessor's completion time.
        for attempt in range(len(_stages(plan))+3):
            runner.progress(round=len(rounds))
            packet = runner.run_plan(plan, role="packet_representative", allow_provisional=packet_candidates)
            windows = {stage["id"]: {"start_ns": stage["start_ns"], "finish_ns": stage["finish_ns"]}
                       for stage in packet["schedule"]}
            conflicts = dag_plan.find_cross_group_conflicts(plan, windows)
            rounds.append({"round": len(rounds), "mode": "packet",
                           "group_count": len(_groups(plan)), "conflicts": conflicts})
            if conflicts:
                plan = refine(plan, conflicts, packet_candidates)
                continue
            needs_packet_witness = (validate or (packet_candidates and _provisional(packet["plan"]))
                                    or deduplication_validation["packet"]["fallback"])
            if needs_packet_witness:
                no_dedup = runner.run_plan(_deduplicate(packet["plan"], enabled=False, mode="packet"),
                                           role="split_no_dedup", use_cache=False)
                comparisons = {"dedup_vs_split_no_dedup": compare_results(no_dedup, packet)}
                _write_json(runner.run_dir / "reference_split_no_dedup.json", no_dedup)
                if validate:
                    if whole is None:
                        whole_plan = dag_plan.refine_groups(plan, [(a["id"], b["id"])
                            for a, b in zip(_stages(plan), _stages(plan)[1:])])
                        whole = runner.run_plan(_deduplicate(whole_plan, enabled=False, mode="packet"),
                                                role="whole_dag_reference", use_cache=False)
                        _write_json(runner.run_dir / "reference_whole_dag.json", whole)
                    comparisons.update(split_vs_whole_dag=compare_results(whole, no_dedup),
                                       dedup_vs_whole_dag=compare_results(whole, packet))
                    validation = {"performed": True, "passed": all(item["passed"] for item in comparisons.values()),
                                  "whole_dag": whole["summary"], "split_no_dedup": no_dedup["summary"],
                                  "comparisons": comparisons}
                    packet_passed = validation["passed"]
                else:
                    packet_passed = comparisons["dedup_vs_split_no_dedup"]["passed"]
                    _write_json(runner.run_dir / "dedup_packet_witness_comparison.json",
                                comparisons["dedup_vs_split_no_dedup"])
                if not packet_passed and packet_candidates and _provisional(packet["plan"]):
                    save_candidate_failure("packet", packet, no_dedup, comparisons)
                    packet_candidates = False
                    mixed_candidates = False
                    plan = _deduplicate(plan, enabled=deduplicate, allow_provisional=False, mode="packet")
                    continue
                if not packet_passed and not validate:
                    raise DagExecutionError("Packet deduplication witness disagreed even after strict fallback; inspect saved evidence")
                record_mode("packet", packet, True, packet_passed, "reference_split_no_dedup.json")
            else:
                record_mode("packet", packet, False, None)
            result = packet
            if not mixed or validation["passed"] is False:
                break
            mixed_plan = _deduplicate(packet["plan"], enabled=deduplicate, allow_provisional=mixed_candidates, mode="mixed")
            result = runner.run_plan(mixed_plan, mixed=True, role="mixed_representative",
                                     allow_provisional=mixed_candidates)
            windows = {stage["id"]: {"start_ns": stage["start_ns"], "finish_ns": stage["finish_ns"]}
                       for stage in result["schedule"]}
            conflicts = dag_plan.find_cross_group_conflicts(plan, windows)
            rounds.append({"round": len(rounds), "mode": "mixed",
                           "group_count": len(_groups(plan)), "conflicts": conflicts})
            if conflicts:
                _write_json(runner.run_dir / f"mixed_conflict_round{attempt}.json", result)
                plan = refine(plan, conflicts, packet_candidates)
                continue
            if _mixed_witness_required(result["plan"]) or deduplication_validation["mixed"]["fallback"]:
                witness = runner.run_plan(_deduplicate(result["plan"], enabled=False, mode="mixed"), mixed=True,
                                           role="mixed_no_dedup_witness", use_cache=False)
                comparison = compare_results(witness, result, compare_steady=True)
                _write_json(runner.run_dir / "reference_mixed_no_dedup.json", witness)
                if not comparison["passed"]:
                    save_candidate_failure("mixed", result, witness, comparison)
                    if not mixed_candidates:
                        raise DagExecutionError("Mixed-granularity witness disagreed even after strict fallback; inspect saved evidence")
                    mixed_candidates = False
                    continue
                _write_json(runner.run_dir / "dedup_mixed_witness_comparison.json", comparison)
                record_mode("mixed", result, True, True, "dedup_mixed_witness_comparison.json")
            else:
                record_mode("mixed", result, False, None)
            performance_packet = packet
            performance_file = "packet_results.json"
            if _representative_layout(packet) != _representative_layout(result):
                performance_packet = runner.run_plan(result["plan"], role="packet_performance_reference",
                    allow_provisional=True, restrict_to_plan=True)
                performance_file = "packet_performance_reference.json"
                _write_json(runner.run_dir / performance_file, performance_packet)
            performance_comparison = compare_results(packet, performance_packet)
            matching_inputs = _representative_layout(performance_packet) == _representative_layout(result)
            performance_valid = performance_comparison["passed"] and matching_inputs
            performance_reference = {"evidence_file": performance_file,
                "summary": performance_packet["summary"], "comparison": performance_comparison,
                "matched_representative_inputs": matching_inputs, "valid": performance_valid}
            packet_runtime = performance_packet["summary"]["simulation_wall_time_ns"]
            mixed_runtime = result["summary"]["simulation_wall_time_ns"]
            transition_count = sum(local.get("execution_metadata", {}).get("transition_count", 0) > 0
                                   for local in result["representative_results"].values())
            mixed_comparison = {"performed": True, **compare_results(packet, result),
                                "cross_group_conflicts": conflicts,
                                "packet_makespan_ns": packet["summary"]["makespan_ns"],
                                "mixed_makespan_ns": result["summary"]["makespan_ns"],
                                "packet_wall_time_seconds": performance_packet["summary"]["representative_process_wall_time_seconds"],
                                "mixed_wall_time_seconds": result["summary"]["representative_process_wall_time_seconds"],
                                "packet_simulation_wall_time_ns": packet_runtime,
                                "mixed_simulation_wall_time_ns": mixed_runtime,
                                "runtime_speedup": packet_runtime/mixed_runtime if mixed_runtime and performance_valid else None,
                                "runtime_speedup_reason": None if mixed_runtime and performance_valid else
                                    "No validated packet timing for the identical representative inputs and release profiles",
                                "runtime_speedup_basis": "sum_of_simulator_run_wall_time_ns",
                                "performance_reference": performance_reference,
                                "acceleration_occurred": transition_count > 0,
                                "representative_execution": {
                                    rep_id: local.get("execution_metadata", {})
                                    for rep_id, local in result["representative_results"].items()},
                                "representatives_with_transitions": transition_count}
            _write_json(runner.run_dir / "packet_results.json", packet)
            break
        else:
            raise DagExecutionError("DAG conflict refinement failed to converge")
        result.update(success=validation["passed"] is not False, validation=validation,
                      mixed_comparison=mixed_comparison, refinement_rounds=rounds,
                      deduplication_validation=deduplication_validation)
        plan = result["plan"]
        result["execution_plan"] = deepcopy(plan_projection(plan))
        if validation["passed"] is False:
            result["error"] = "Packet validation failed; inspect per-flow differences before enabling mixed granularity"
        result["summary"]["representative_phase_wall_time_seconds"] = result["summary"]["wall_time_seconds"]
        result["summary"]["wall_time_seconds"] = time.monotonic()-runner.started
        result["summary"]["executed_jobs"] = len(runner.jobs)
        runner.monitor.finish()
        runner.progress(phase="completed" if result["success"] else "validation_failed",
                        **result["summary"], representatives=[{key: rep[key] for key in
                            ("id", "group_id", "member_group_ids")} for rep in _representatives(plan)])
        result["monitor"] = runner.monitor.snapshot()
        _write_json(runner.run_dir / "plan.json", plan)
        _write_json(runner.run_dir / "results.json", result)
        runner.manifest.update(success=result["success"], final_input_fingerprint=plan.get("input_fingerprint"),
                               result_file=str(runner.run_dir / "results.json"))
        _write_json(runner.run_dir / "manifest.json", runner.manifest)
        return result
    except BaseException as exc:
        runner.abort.set()
        with runner.state.lock:
            for process in list(runner.state.processes):
                terminate_process(process)
        runner.monitor.finish()
        runner.progress(phase="cancelled" if isinstance(exc, DagCancelled) else "failed", error=str(exc))
        _write_json(runner.run_dir / "error.json", {"success": False, "error": str(exc),
                                                   "execution": runner.execution})
        runner.manifest.update(success=False, error=str(exc))
        _write_json(runner.run_dir / "manifest.json", runner.manifest)
        raise


def run_packet_baseline(plan, project_root, run_dir, *, monitor=None, state=None,
                        build=False, job_timeout=3600, simulation_id=None,
                        job_executor=None):
    """Run the complete frozen DAG once in a fresh packet-level network.

    This analysis-only baseline has one group, one representative, and one
    native simulation job. It never launches split witnesses or calibration
    jobs. The caller must supply a separate state/monitor from the live
    experiment when it needs cancellation or progress reporting.
    """
    stages = _stages(plan)
    if not stages:
        raise DagExecutionError("A packet baseline requires at least one logical stage")
    merged = dag_plan.refine_groups(deepcopy(plan), [(a["id"], b["id"])
        for a, b in zip(stages, stages[1:])])
    baseline_plan = _deduplicate(merged, enabled=False, allow_provisional=False, mode="packet")
    runner = _Runner(baseline_plan, project_root, run_dir, workers=1,
                     monitor=monitor, state=state, job_timeout=job_timeout,
                     job_executor=job_executor, simulation_id=simulation_id)
    policy = {"enable_cut": False, "enable_mixed_granularity": False, "deduplicate": False}
    runner.manifest.update(purpose="analysis_whole_dag_baseline", baseline_policy=policy)
    _write_json(runner.run_dir / "manifest.json", runner.manifest)
    try:
        runner.check()
        if build:
            runner.build()
        runner.fingerprint()
        if job_executor is None and baseline_plan.get("route_certificate", {}).get("certified") is not True:
            raise DagExecutionError("A packet baseline requires the frozen native route certificate")
        result = runner.run_plan(baseline_plan, mixed=False,
                                 role="analysis_whole_dag_baseline", use_cache=False)
        if len(runner.jobs) != 1 or result["summary"]["group_count"] != 1:
            raise DagExecutionError("A packet baseline must execute exactly one complete DAG job")
        if job_executor is None and not all(local.get("route_verification", {}).get("passed") is True
                                           for local in result["representative_results"].values()):
            raise DagExecutionError("The packet baseline native routes were not verified")
        runner.check()
        result.update(success=True, mode="dag", baseline_policy=policy,
                      validation={"performed": False, "passed": None},
                      mixed_comparison={"performed": False},
                      refinement_rounds=[])
        result["execution_plan"] = deepcopy(plan_projection(result["plan"]))
        result["summary"]["representative_phase_wall_time_seconds"] = result["summary"]["wall_time_seconds"]
        result["summary"]["wall_time_seconds"] = time.monotonic()-runner.started
        result["summary"]["executed_jobs"] = len(runner.jobs)
        runner.monitor.finish()
        runner.progress(phase="completed", **result["summary"], representatives=[
            {key: rep[key] for key in ("id", "group_id", "member_group_ids")}
            for rep in _representatives(result["plan"])])
        result["monitor"] = runner.monitor.snapshot()
        _write_json(runner.run_dir / "plan.json", result["plan"])
        _write_json(runner.run_dir / "results.json", result)
        runner.manifest.update(success=True,
                               final_input_fingerprint=result["plan"].get("input_fingerprint"),
                               result_file=str(runner.run_dir / "results.json"))
        _write_json(runner.run_dir / "manifest.json", runner.manifest)
        return result
    except BaseException as exc:
        runner.abort.set()
        with runner.state.lock:
            for process in list(runner.state.processes):
                terminate_process(process)
        runner.monitor.finish()
        runner.progress(phase="cancelled" if isinstance(exc, DagCancelled) else "failed", error=str(exc))
        _write_json(runner.run_dir / "error.json", {"success": False, "error": str(exc),
                                                   "execution": runner.execution})
        runner.manifest.update(success=False, error=str(exc))
        _write_json(runner.run_dir / "manifest.json", runner.manifest)
        raise
