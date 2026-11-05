"""On-demand whole-DAG packet baselines, isolated from live experiment state."""
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import statistics
import threading
import time
from types import SimpleNamespace
import uuid

from .dag_routes import native_runtime_fingerprint
from .dag_runner import DagCancelled, compare_results, terminate_process


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _runtime_evidence(result):
    evidence = set()
    plan = result.get("plan", {})
    certificate = plan.get("route_certificate", {})
    if certificate.get("native_runtime_sha256"):
        evidence.add(certificate["native_runtime_sha256"])
    representatives = result.get("representative_results", {})
    if not representatives:
        evidence.add("<missing-runtime-evidence>")
    for local in representatives.values():
        fingerprint = local.get("evidence_context", {}).get("native_runtime_sha256")
        if fingerprint:
            evidence.add(fingerprint)
        else:
            evidence.add("<missing-runtime-evidence>")
    return evidence


def _semantic_plan(plan):
    """Paths, partitions and derived boundary releases are not traffic inputs."""
    stages = []
    for stage in plan["stages"]:
        operations = []
        for index, operation in enumerate(stage["operations"]):
            operations.append({"id": operation["id"], "index": operation.get("index", index),
                "predecessors": operation.get("predecessors", []),
                "phases": [[{field: flow[field] for field in
                    ("src", "dst", "sport", "dport", "priority", "msg_len")}
                    for flow in phase] for phase in operation["phases"]]})
        stages.append({"id": stage["id"], "predecessors": stage.get("predecessors", []),
                       "operations": operations})
    config = re.sub(r"(?m)^TOPOLOGY_FILE\s+.*$", "TOPOLOGY_FILE <frozen-topology>",
                    plan.get("config_text", ""))
    return {"schema": "whole_packet_baseline_v1", "stages": stages, "edges": plan["edges"],
            "topology": plan.get("topology"), "topology_text": plan.get("topology_text"),
            "config_text": config, "empty_network": plan.get("empty_network", True),
            "original_boundary_releases": plan.get("boundary_releases", {})}


def _flow_identity(flow):
    return tuple(flow[field] for field in ("stage_id", "operation_index", "phase_index",
        "flow_index", "src", "dst", "sport", "dport", "priority", "size_bytes"))


def _expected_flows(plan):
    return Counter((stage["id"], operation.get("index", oi), pi, fi,
                    flow["src"], flow["dst"], flow["sport"], flow["dport"],
                    flow["priority"], flow["msg_len"])
                   for stage in plan["stages"] for oi, operation in enumerate(stage["operations"])
                   for pi, phase in enumerate(operation["phases"]) for fi, flow in enumerate(phase))


def _validate_baseline(result, plan, runtime, *, allow_legacy_reference=False):
    """A complete packet experiment is required, never a partial/accelerated run."""
    legacy = allow_legacy_reference and "success" not in result
    if result.get("success") is not True and not legacy:
        raise ValueError("包级基线未成功完成")
    own_plan = result["plan"]
    if _semantic_plan(own_plan) != _semantic_plan(plan):
        raise ValueError("基线输入、依赖或原始释放时刻与冻结实验不一致")
    if len(own_plan["groups"]) != 1 or len(own_plan["representatives"]) != 1:
        raise ValueError("基线必须是不切分、不去重的完整 DAG")
    if {stage["id"] for stage in own_plan["stages"]} != {stage["id"] for stage in plan["stages"]}:
        raise ValueError("基线没有覆盖当前实验的全部阶段")
    if Counter(_flow_identity(flow) for flow in result["flows"]) != _expected_flows(plan):
        raise ValueError("基线流量集合与冻结实验不一致")
    if result["summary"].get("total_flows") != len(result["flows"]):
        raise ValueError("基线流量记录不完整")
    for flow in result["flows"]:
        if (min(flow["start_ns"], flow["finish_ns"], flow["fct_ns"]) < 0 or
                flow["finish_ns"]-flow["start_ns"] != flow["fct_ns"]):
            raise ValueError("基线流量时间戳无效")
    expected_operations = {(stage["id"], op.get("index", index))
                           for stage in plan["stages"] for index, op in enumerate(stage["operations"])}
    actual_operations = [(op["stage_id"], op["operation_index"]) for op in result["operations"]]
    if set(actual_operations) != expected_operations or len(actual_operations) != len(expected_operations):
        raise ValueError("基线操作记录不完整")
    if {item["id"] for item in result["schedule"]} != {stage["id"] for stage in plan["stages"]}:
        raise ValueError("基线阶段记录不完整")
    if result["summary"].get("mixed_granularity") is not False:
        raise ValueError("基线必须关闭混合粒度")
    representatives = result.get("representative_results", {})
    if len(representatives) != 1 or _runtime_evidence(result) != {runtime}:
        raise ValueError("基线运行时证据不完整或不匹配")
    for local in representatives.values():
        if legacy and local.get("route_verification", {}).get("passed") is not True:
            raise ValueError("旧完整基线缺少成功的原生路由核验证据")
        metadata = local["execution_metadata"]
        if (metadata.get("mixed_requested") is not False or metadata.get("transition_count") != 0
                or metadata.get("completed_operations") != len(expected_operations)
                or metadata.get("operation_count") != len(expected_operations)):
            raise ValueError("基线不是完整的纯包级运行")


class BaselineManager:
    """One background job per frozen-input/runtime key, with persistent results."""
    def __init__(self, cache_root, project_root, *, runner=None, runtime_provider=None):
        self.cache_root = Path(cache_root).resolve()
        self.project_root = Path(project_root).resolve()
        self.runner = runner
        self.runtime_provider = runtime_provider or native_runtime_fingerprint
        self.lock = threading.RLock()
        self.jobs = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="packet-baseline")

    def _descriptor(self, experiment, run_dir):
        if experiment.get("success") is not True:
            raise ValueError("请先成功完成当前实验后再分析")
        run_dir = Path(run_dir).resolve()
        snapshot = run_dir/"input_plan.json"
        plan = json.loads(snapshot.read_text(encoding="utf-8")) if snapshot.is_file() else deepcopy(experiment.get("plan"))
        if not isinstance(plan, dict) or not plan.get("stages"):
            raise ValueError("实验缺少冻结输入，请重新运行实验")
        runtime_info = self.runtime_provider(self.project_root)
        runtime = runtime_info["native_runtime_sha256"]
        if not runtime or _runtime_evidence(experiment) != {runtime}:
            raise ValueError("仿真程序与当前实验的运行时证据不一致，请重新运行实验")
        semantic = _semantic_plan(plan)
        signature = _digest({"input": semantic, "runtime": runtime})
        return {"plan": plan, "semantic": semantic, "cache_key": signature,
                "runtime": runtime, "runtime_info": runtime_info, "run_dir": run_dir,
                "directory": self.cache_root/signature}

    def _cached(self, descriptor):
        path = descriptor["directory"]/"result.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (saved["cache_key"] != descriptor["cache_key"] or
                    saved["native_runtime_sha256"] != descriptor["runtime"] or
                    saved["result_sha256"] != _digest(saved["baseline"])):
                return None
            _validate_baseline(saved["baseline"], descriptor["plan"], descriptor["runtime"])
            return saved
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _status(key, *, status="not_started", reused=False, **details):
        return {"success": True, "cache_key": key, "status": status,
                "is_running": status == "running", "has_baseline": status == "completed",
                "needs_refresh": status != "completed", "reused": reused, **details}

    def status(self, experiment, run_dir):
        descriptor = self._descriptor(experiment, run_dir)
        key = descriptor["cache_key"]
        with self.lock:
            entry = self.jobs.get(key)
            if entry is not None and entry["status"] != "completed":
                return self._status(key, status=entry["status"],
                    last_started=entry.get("started"), last_finished=entry.get("finished"),
                    error=entry.get("error"), source=entry.get("source"))
            cached = self._cached(descriptor)
            if cached:
                return self._status(key, status="completed", reused=True,
                                    last_finished=cached.get("completed_at"), source=cached["source"])
        return self._status(key)

    def any_running(self):
        with self.lock:
            return any(entry["status"] == "running" for entry in self.jobs.values())

    def get_or_run(self, experiment, run_dir):
        descriptor = self._descriptor(experiment, run_dir)
        key = descriptor["cache_key"]
        with self.lock:
            entry = self.jobs.get(key)
            if entry is not None and entry["status"] == "running":
                return entry["future"]
            cached = self._cached(descriptor)
            if cached:
                future = Future()
                future.set_result({"baseline": cached["baseline"], "baseline_status": self._status(
                    key, status="completed", reused=True, source=cached["source"],
                    last_finished=cached["completed_at"])})
                return future
            state = SimpleNamespace(cancelled=False, lock=threading.RLock(), processes=set(), execution={})
            entry = {"status": "running", "started": time.time(), "state": state, "error": None}
            self.jobs[key] = entry
            entry["future"] = self.executor.submit(self._run, descriptor, deepcopy(experiment), entry)
            return entry["future"]

    def _run(self, descriptor, experiment, entry):
        key = descriptor["cache_key"]
        try:
            baseline = None
            source = "new_baseline"
            old_whole = descriptor["run_dir"]/"reference_whole_dag.json"
            candidates = []
            if old_whole.is_file():
                try:
                    candidates.append(("existing_whole_reference", json.loads(old_whole.read_text(encoding="utf-8"))))
                except (OSError, ValueError):
                    pass
            candidates.append(("existing_whole_experiment", experiment))
            for candidate_source, candidate in candidates:
                try:
                    _validate_baseline(candidate, descriptor["plan"], descriptor["runtime"],
                                       allow_legacy_reference=candidate_source == "existing_whole_reference")
                    # Re-evaluate semantic input as well as output population;
                    # equal flow identities alone do not prove equal dependencies.
                    if _semantic_plan(candidate["plan"]) != descriptor["semantic"]:
                        continue
                    baseline, source = {**candidate, "success": True}, candidate_source
                    break
                except (ValueError, KeyError, TypeError):
                    continue
            if entry["state"].cancelled:
                raise DagCancelled("包级基线已取消")
            if baseline is None:
                if self.runner is None:
                    from .dag_runner import run_packet_baseline
                    runner = run_packet_baseline
                else:
                    runner = self.runner
                attempt = descriptor["directory"]/("attempt-"+uuid.uuid4().hex)
                baseline = runner(deepcopy(descriptor["plan"]), self.project_root, attempt,
                                  state=entry["state"], build=False,
                                  simulation_id="baseline_"+key[:16])
            _validate_baseline(baseline, descriptor["plan"], descriptor["runtime"])
            if self.runtime_provider(self.project_root)["native_runtime_sha256"] != descriptor["runtime"]:
                raise ValueError("基线运行期间仿真程序发生变化，请重新运行实验")
            with self.lock:
                if entry["state"].cancelled:
                    raise DagCancelled("包级基线已取消")
                finished = time.time()
                saved = {"schema_version": 1, "cache_key": key,
                    "native_runtime_sha256": descriptor["runtime"], "completed_at": finished,
                    "source": source, "baseline": baseline, "result_sha256": _digest(baseline)}
                _atomic_json(descriptor["directory"]/"result.json", saved)
                entry.update(status="completed", finished=finished, source=source)
                entry.pop("future", None)
            return {"baseline": baseline, "baseline_status": self._status(key, status="completed",
                reused=source != "new_baseline", source=source,
                last_started=entry["started"], last_finished=finished)}
        except BaseException as exc:
            with self.lock:
                entry.update(status="cancelled" if entry["state"].cancelled or isinstance(exc, DagCancelled)
                             else "failed", finished=time.time(), error=str(exc))
                entry.pop("future", None)
            raise

    def cancel(self, experiment, run_dir):
        key = self._descriptor(experiment, run_dir)["cache_key"]
        with self.lock:
            entry = self.jobs.get(key)
            if entry is None or entry["status"] != "running":
                return False
            entry["state"].cancelled = True
            future = entry.get("future")
            if future is not None and future.cancel():
                entry.update(status="cancelled", finished=time.time(), error="包级基线已取消")
            state = entry["state"]
        with state.lock:
            processes = list(state.processes)
        for process in processes:
            terminate_process(process)
        return True

    def shutdown(self):
        with self.lock:
            for entry in self.jobs.values():
                if entry["status"] == "running":
                    entry["state"].cancelled = True
        self.executor.shutdown(wait=True, cancel_futures=True)


def _fct_analysis(result):
    values = [flow["fct_ns"]/1000 for flow in sorted(result["flows"], key=_flow_identity)]
    return {"file_found": True, "total_flows": len(values),
            "average_fct_us": statistics.mean(values) if values else None,
            "average_fct_ms": statistics.mean(values)/1000 if values else None,
            "min_fct_us": min(values) if values else None, "max_fct_us": max(values) if values else None,
            "sampled_fct_values": values}


def _performance_analysis(result):
    flows = result["flows"]
    nodes = result.get("plan", {}).get("topology", {}).get("nodes", [])
    return {"has_data": True, **result["summary"],
            "network_config": {"server_count": sum(node.get("role") == "host" for node in nodes)},
            "flow_statistics": {"total_flows": len(flows),
                "average_flow_size_MB": statistics.mean(flow["size_bytes"] for flow in flows)/1048576
                    if flows else 0}}


def _steady_analysis(result):
    run_id = result.get("monitor", {}).get("simulation_id")
    entries = {}
    for local in result.get("representative_results", {}).values():
        for index, event in enumerate(local.get("steady_events", [])):
            if event.get("event") != "enter":
                continue
            identifier = f"{run_id}:{event['task_id']}:{index}"
            entries[identifier] = {**event, "simulation_id": run_id,
                                   "event_id": identifier, "source": "simulator"}
    logical_times = [event["global_sim_time_ns"] for event in result.get("steady_state_timeline", [])
                     if event.get("event") == "enter"]
    return {"file_found": True, "is_system_steady": bool(entries),
            "steady_state_count": len(entries), "steady_wall_times": list(entries.values()),
            "steady_state_time_ns": min(logical_times) if logical_times else None,
            "steady_times_ns": logical_times}


def analyze_dag_results(experiment, baseline, baseline_status):
    comparison = compare_results(baseline, experiment)
    references = {_flow_identity(flow): flow for flow in baseline["flows"]}
    candidates = {_flow_identity(flow): flow for flow in experiment["flows"]}
    if len(references) != len(baseline["flows"]) or len(candidates) != len(experiment["flows"]):
        raise ValueError("流量标识重复，无法逐流比较")
    errors, per_flow = [], []
    for identity in references.keys() & candidates.keys():
        expected, actual = references[identity], candidates[identity]
        delta = actual["fct_ns"]-expected["fct_ns"]
        relative = abs(delta)/expected["fct_ns"] if expected["fct_ns"] else (0 if not delta else None)
        if relative is not None:
            errors.append(relative*100)
        per_flow.append({"stage_id": identity[0], "operation_index": identity[1],
            "phase_index": identity[2], "flow_index": identity[3], "src": identity[4], "dst": identity[5],
            "packet_fct_ns": expected["fct_ns"], "experiment_fct_ns": actual["fct_ns"],
            "fct_delta_ns": delta, "abs_relative_fct_error_percent": relative*100 if relative is not None else None})
    population_match = comparison["missing_flows"] == comparison["extra_flows"] == 0
    valid_error_summary = population_match and len(errors) == len(baseline["flows"])
    errors.sort()
    packet_native = baseline["summary"].get("simulation_wall_time_ns", 0)
    experiment_native = experiment["summary"].get("simulation_wall_time_ns", 0)
    packet_wall = baseline["summary"].get("wall_time_seconds", 0)
    experiment_wall = experiment["summary"].get("wall_time_seconds", 0)
    comparison.update(packet_makespan_ns=baseline["summary"]["makespan_ns"],
        experiment_makespan_ns=experiment["summary"]["makespan_ns"], flow_population_match=population_match,
        max_abs_fct_error_ns=comparison["max_fct_error_ns"],
        max_abs_relative_fct_error_percent=max(errors) if errors and valid_error_summary else None,
        mean_abs_relative_fct_error_percent=statistics.mean(errors) if errors and valid_error_summary else None,
        p95_abs_relative_fct_error_percent=errors[int(.95*(len(errors)-1))] if errors and valid_error_summary else None,
        fct_fidelity=1-statistics.mean(errors)/100 if errors and valid_error_summary else None,
        runtime_speedup=packet_native/experiment_native if packet_native and experiment_native else None,
        total_runtime_speedup=packet_wall/experiment_wall if packet_wall and experiment_wall else None,
        runtime_speedup_basis="whole_packet_native_time / executed_experiment_representatives_native_time",
        total_runtime_speedup_basis="whole_packet_wall_time / experiment_workflow_wall_time",
        packet_simulation_wall_time_ns=packet_native, experiment_simulation_wall_time_ns=experiment_native,
        per_flow=sorted(per_flow, key=lambda row:(row["stage_id"],row["operation_index"],row["phase_index"],row["flow_index"])))
    return {"dag_result": experiment, "fct_analysis": _fct_analysis(experiment),
            "performance_analysis": _performance_analysis(experiment),
            "steady_state_analysis": _steady_analysis(experiment),
            "baseline_analysis": {"fct_analysis": _fct_analysis(baseline),
                "performance_analysis": _performance_analysis(baseline), "summary": baseline["summary"]},
            "baseline_status": baseline_status, "comparison": comparison}
