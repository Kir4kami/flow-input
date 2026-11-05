import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "examples/Reverie"))
from api import complete_api as api
from api.simulation_monitor import SteadyStateMonitor


def write_event(run_dir, task=1, kind="enter", ns=100, wall=1700000000.0):
    path = run_dir / f"task{task}" / "steady_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(task_id=task, event=kind, sim_time_ns=ns,
                                     wall_clock_ts=wall)) + "\n")
    return path


def test_fast_transitions_and_identical_times_are_retained(tmp_path):
    monitor = SteadyStateMonitor()
    monitor.reset(tmp_path, 4, "run1")
    for task in range(1, 5):
        write_event(tmp_path, task)
        write_event(tmp_path, task, "exit", 101)
    snapshot = monitor.snapshot()
    assert snapshot["steady_state_count"] == 4
    assert not snapshot["is_steady"]
    assert len({event["event_id"] for event in snapshot["history"]}) == 4
    assert monitor.snapshot()["revision"] == snapshot["revision"]
    assert monitor.analysis()["steady_state_count"] == 4


def test_partial_records_and_bad_records(tmp_path):
    monitor = SteadyStateMonitor()
    monitor.reset(tmp_path, 1, "run1")
    path = tmp_path / "task1/steady_events.jsonl"
    path.parent.mkdir()
    record = json.dumps(dict(task_id=1, event="enter", sim_time_ns=5, wall_clock_ts=10))
    path.write_text(record[:30], encoding="utf-8")
    assert monitor.snapshot()["steady_state_count"] == 0
    with path.open("a", encoding="utf-8") as stream:
        stream.write(record[30:] + "\ninvalid json\n")
        stream.write('{"task_id":1,"event":"enter","sim_time_ns":NaN,"wall_clock_ts":10}\n')
    assert monitor.snapshot()["steady_state_count"] == 1
    assert monitor.snapshot()["steady_state_count"] == 1


def test_new_run_does_not_read_old_events_and_finish_clears_current_state(tmp_path):
    monitor = SteadyStateMonitor()
    monitor.reset(tmp_path / "old", 1, "old")
    write_event(tmp_path / "old")
    assert monitor.snapshot()["is_steady"]
    monitor.finish()
    assert not monitor.snapshot()["is_steady"]
    assert monitor.snapshot()["steady_state_count"] == 1
    monitor.reset(tmp_path / "new", 4, "new")
    assert monitor.snapshot()["steady_state_count"] == 0


def test_completed_task_is_no_longer_steady_while_other_tasks_run(tmp_path):
    monitor = SteadyStateMonitor()
    monitor.reset(tmp_path, 4, "run1")
    write_event(tmp_path, 1)
    write_event(tmp_path, 2)
    assert monitor.snapshot()["steady_task_count"] == 2
    (tmp_path / "task1/exit_code").write_text("0\n")
    snapshot = monitor.snapshot()
    assert snapshot["steady_task_count"] == 1
    assert snapshot["details"][0]["completed"]
    assert snapshot["steady_state_count"] == 2


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project with spaces"
    reverie = root / "examples/Reverie"
    (reverie / "api").mkdir(parents=True)
    for script in ("sim.sh", "kira-parallel.sh"):
        shutil.copyfile(REPO / "examples/Reverie" / script, reverie / script)
    for task in range(1, 5):
        directory = reverie / f"task{task}"
        directory.mkdir()
        (directory / "rdma_operate0.txt").write_text("input\n")
        (directory / "dependence.txt").write_text("0\n")
    for key, value in dict(REVERIE_ROOT=reverie, PROJECT_ROOT=root,
                           API_DIR=reverie / "api", SRC_ROOT=root / "src",
                           ECMP_CACHE_FILE=reverie / "api/ecmp_paths_cache.json",
                           simulation_status=api.SimulationStatus(),
                           steady_state_monitor=SteadyStateMonitor()).items():
        monkeypatch.setattr(api, key, value)
    return root, reverie


def test_actual_endpoints_share_state_and_keep_per_task_history(project):
    root, reverie = project
    run = reverie / "dump/runs/current"
    api.steady_state_monitor.reset(run, 4, "current")
    api.simulation_status.current_task = "current"
    api.simulation_status.is_running = True
    # Old root data must not become live data for this run.
    (root / "flow_stats.txt").write_text("STALE")
    for task in range(1, 5):
        write_event(run, task)
    with TestClient(api.app) as client:
        monitor = client.get("/steady-state-monitor").json()
        status = client.get("/simulation-status").json()
        assert monitor["steady_task_count"] == 4
        assert status["steady_state"] is True
        assert status["monitor"]["revision"] == monitor["revision"]
        assert len(client.get("/steady-state-history").json()["history"]) == 4
        assert client.get("/flow_stats_txt").status_code == 404
        path = run / "task2/flow_stats.txt"
        path.write_text("TASK2")
        assert client.get("/flow_stats_txt?task_id=2").text == "TASK2"
        assert client.get("/flow_stats_txt?task_id=5").status_code == 400
        for task in range(1, 5):
            write_event(run, task, "exit", 101)
        assert not client.get("/simulation-status").json()["steady_state"]
        assert client.get("/steady-state-monitor").json()["steady_state_count"] == 4


def test_start_reserves_run_and_passes_both_options(project, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "run_simulation", lambda *args, **kwargs: calls.append(args))
    with TestClient(api.app) as client:
        response = client.post("/run-simulation", json={"task_num": 4,
                               "enable_mixed_granularity": True})
        assert response.status_code == 200
        assert calls[0][1] == 4 and calls[0][3] is True
        assert client.post("/run-simulation", json={"task_num": 4}).status_code == 400
        assert client.get("/steady-state-monitor").json()["task_count"] == 4


def test_cancelled_queued_run_cannot_start_or_change_the_next_run(project, monkeypatch):
    worker = api.run_simulation
    pending = []
    monkeypatch.setattr(api, "run_simulation", lambda *args, **kwargs: pending.append((args, kwargs)))
    with TestClient(api.app) as client:
        first = client.post("/run-simulation", json={"task_num": 4}).json()
        assert client.post("/stop-simulation").status_code == 200
        second = client.post("/run-simulation", json={"task_num": 1}).json()
        args, kwargs = pending[0]
        assert not worker(*args, **kwargs)["success"]
        status = client.get("/simulation-status").json()
        assert status["simulation_id"] == second["simulation_id"] != first["simulation_id"]
        assert status["is_running"]
        assert status["monitor"]["task_count"] == 1


@pytest.fixture(scope="module")
def cpp_probe(tmp_path_factory):
    directory = tmp_path_factory.mktemp("cpp-probe")
    source = directory / "probe.cc"
    source.write_text(r'''
#include "mixed-granularity.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif
int main() {
    std::cout << "mixed=" << ns3::IsMixedGranularityEnabled() << std::endl;
    const char* task = std::getenv("FLOW_INPUT_TASK_ID");
    const std::string id = task ? task : "1";
    ns3::RecordSteadyStateEvent("enter", 100);
#ifdef _WIN32
    Sleep(200);
#else
    usleep(200000);
#endif
    ns3::RecordSteadyStateEvent("exit", 101);
    std::ofstream(ns3::GetSimulationOutputPath("flow_stats.txt")) << "task" << id;
    std::ofstream(ns3::GetSimulationOutputPath("evaluation.fct" + id)) << id << "\n";
    std::ofstream(ns3::GetSimulationOutputPath("system" + id + ".log")) << "total time: 200 ms\n";
}
''', encoding="utf-8")
    executable = directory / ("probe.exe" if os.name == "nt" else "probe")
    compiler = shutil.which("g++")
    assert compiler, "C++ compiler required for the event-writer regression tests"
    subprocess.run([compiler, "-std=c++17", "-iquote", str(REPO / "src/core/model"),
                    str(source), str(REPO / "src/core/model/mixed-granularity.cc"),
                    "-o", str(executable)], check=True, capture_output=True, text=True)
    return executable


@pytest.mark.parametrize("enabled", ["0", "1"])
def test_compiled_cpp_switch_and_real_timestamps(tmp_path, cpp_probe, enabled):
    env = dict(os.environ, FLOW_INPUT_MIXED_GRANULARITY=enabled,
               FLOW_INPUT_OUTPUT_DIR=str(tmp_path), FLOW_INPUT_TASK_ID="3")
    before = time.time()
    result = subprocess.run([str(cpp_probe)], env=env, check=True, capture_output=True, text=True)
    assert f"mixed={enabled}" in result.stdout
    records = [json.loads(line) for line in (tmp_path / "steady_events.jsonl").read_text().splitlines()]
    assert [record["event"] for record in records] == ["enter", "exit"]
    assert all(record["task_id"] == 3 and before <= record["wall_clock_ts"] <= time.time()
               for record in records)


@pytest.mark.parametrize("task_num,enabled,fail_task", [(1, False, 0), (4, True, 0), (4, True, 3)])
def test_shell_cpp_api_pipeline(project, monkeypatch, cpp_probe, task_num, enabled, fail_task):
    root, reverie = project
    bash = (Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt"
            else Path(shutil.which("bash")))
    assert bash.exists()
    # This stand-in replaces only ns-3's network computation. The production
    # shell, API, compiled C++ event writer and monitor execute unmodified.
    fake_ns3 = root / "ns3"
    fake_ns3.write_text('''#!/usr/bin/env bash
set -eu
if [[ "$1" == build ]]; then echo build >> build_calls; exit 0; fi
[[ "$1" == run && "$2" == --no-build ]]
"$FLOW_INPUT_TEST_PROBE"
[[ "${FLOW_INPUT_FAIL_TASK:-0}" != "$FLOW_INPUT_TASK_ID" ]]
''', encoding="utf-8", newline="\n")
    fake_ns3.chmod(0o755)
    monkeypatch.setenv("FLOW_INPUT_TEST_PROBE", cpp_probe.as_posix())
    monkeypatch.setenv("FLOW_INPUT_FAIL_TASK", str(fail_task))
    original_popen = subprocess.Popen
    def popen(command, **kwargs):
        return original_popen([str(bash), *command[1:]], **kwargs)
    monkeypatch.setattr(api.subprocess, "Popen", popen)
    simulation_id = "integration"
    api.simulation_status.current_task = simulation_id
    api.simulation_status.is_running = True
    api.simulation_status.run_dir = reverie / "dump/runs/integration"
    api.steady_state_monitor.reset(api.simulation_status.run_dir, task_num, simulation_id)
    results = []
    runner = threading.Thread(target=lambda: results.append(api.run_simulation(
        simulation_id, task_num, "qwen", enabled, 1, True)))
    runner.start()
    saw_live_event = False
    with TestClient(api.app) as client:
        deadline = time.monotonic() + 20
        while runner.is_alive() and time.monotonic() < deadline:
            snapshot = client.get("/simulation-status").json()
            if snapshot["is_running"] and snapshot["monitor"]["history"]:
                saw_live_event = True
            time.sleep(0.02)
        runner.join(timeout=5)
        assert not runner.is_alive()
        assert results[0]["success"] is (fail_task == 0), results[0]
        assert saw_live_event
        snapshot = client.get("/steady-state-monitor").json()
    assert snapshot["steady_state_count"] == task_num
    assert not snapshot["is_steady"]
    assert (root / "build_calls").read_text().splitlines() == ["build"]
    assert len((reverie / "dump/evaluation.fct1").read_text().splitlines()) == task_num
    for task in range(1, task_num + 1):
        output = api.simulation_status.run_dir / f"task{task}"
        assert f"mixed={int(enabled)}" in (output / "evaluation.out").read_text()
        assert (output / "flow_stats.txt").read_text() == f"task{task}"
    if not fail_task:
        history = json.loads((reverie / "dump/steady_state_history.json").read_text(encoding="utf-8"))
        assert len(history["history"]) == task_num
    else:
        assert snapshot["details"][fail_task - 1]["exit_code"] != 0


def test_failed_simulator_is_not_reported_as_success(project, monkeypatch):
    class FailedProcess:
        returncode = 1
        def communicate(self, **kwargs):
            return "", "task 3 failed"
        def poll(self):
            return 1
    monkeypatch.setattr(api.subprocess, "Popen", lambda *args, **kwargs: FailedProcess())
    api.simulation_status.current_task = "failure"
    result = api.run_simulation("failure", 4, "qwen", True, 1, True)
    assert result["success"] is False
    assert "task 3 failed" in result["error"]
    with TestClient(api.app) as client:
        status = client.get("/simulation-status").json()
        assert not status["is_running"]
        assert "task 3 failed" in status["error"]


def test_analysis_uses_structured_history_across_baseline_copy(project):
    _, reverie = project
    dump = reverie / "dump"
    run = dump / "runs/test"
    monitor = SteadyStateMonitor()
    monitor.reset(run, 4, "test")
    for task in range(1, 5):
        write_event(run, task)
    snapshot = monitor.snapshot()
    (dump / "steady_state_history.json").write_text(json.dumps(snapshot))
    backup = reverie / "dump_experiment"
    api._copy_dump_files(dump, backup)
    result = api._collect_analysis_from_dump(backup, "steady_state")["steady_state_analysis"]
    assert len(result["steady_wall_times"]) == 4
    assert {event["task_id"] for event in result["steady_wall_times"]} == {1, 2, 3, 4}
