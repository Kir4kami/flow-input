"""Read the simulator's per-task events without inferring state from sampled rates."""

import json
import math
import threading
import time
from pathlib import Path


class SteadyStateMonitor:
    def __init__(self):
        self._lock = threading.RLock()
        self.reset()

    def reset(self, run_dir=None, task_num=1, simulation_id=None):
        with self._lock:
            self.run_dir = Path(run_dir) if run_dir else None
            self.simulation_id = simulation_id
            self.is_monitoring = run_dir is not None
            self.finished = False
            self.revision = 0
            self.execution_summary = {}
            self.offsets = {}
            self.events = []
            self.tasks = {i: {"task_id": i, "is_steady": False, "steady_state_count": 0,
                              "completed": False, "exit_code": None}
                          for i in range(1, task_num + 1)}

    def register_task(self, task_id, metadata=None):
        """Append an actual representative/reference job without losing history."""
        with self._lock:
            if task_id in self.tasks:
                raise ValueError(f"Task {task_id} is already registered")
            self.tasks[task_id] = {"task_id": task_id, "is_steady": False,
                                   "steady_state_count": 0, "completed": False,
                                   "exit_code": None, **(metadata or {})}
            self.revision += 1

    def refresh(self):
        with self._lock:
            if not self.run_dir or self.finished:
                return
            for task_id, task in self.tasks.items():
                path = self.run_dir / f"task{task_id}" / "steady_events.jsonl"
                if not path.exists():
                    self._read_exit_code(task_id, task)
                    continue
                offset = self.offsets.get(task_id, 0)
                with path.open("rb") as stream:
                    # A run has its own directory; truncation should never happen.
                    if path.stat().st_size < offset:
                        continue
                    stream.seek(offset)
                    while True:
                        start = stream.tell()
                        line = stream.readline()
                        if not line.endswith(b"\n"):
                            self.offsets[task_id] = start
                            break  # retry a partially written record next time
                        self.offsets[task_id] = stream.tell()
                        try:
                            event = json.loads(line)
                            kind = event["event"]
                            sim_time = float(event["sim_time_ns"])
                            wall_time = float(event["wall_clock_ts"])
                            if (event["task_id"] != task_id or kind not in ("enter", "exit")
                                    or not math.isfinite(sim_time) or sim_time < 0
                                    or not math.isfinite(wall_time) or wall_time <= 0):
                                continue
                        except (ValueError, KeyError, TypeError, UnicodeError):
                            continue
                        if kind == "enter":
                            task["steady_state_count"] += 1
                        task["is_steady"] = kind == "enter"
                        event.update(event_id=f"{self.simulation_id}:{task_id}:{start}",
                                     simulation_id=self.simulation_id, source="simulator")
                        self.events.append(event)
                        self.revision += 1
                self._read_exit_code(task_id, task)

    def _read_exit_code(self, task_id, task):
        if task["completed"]:
            return
        path = self.run_dir / f"task{task_id}" / "exit_code"
        try:
            code = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return
        task.update(completed=True, exit_code=code, is_steady=False)
        self.revision += 1

    def finish(self):
        with self._lock:
            self.refresh()
            self.finished = True
            self.is_monitoring = False
            for task in self.tasks.values():
                task["is_steady"] = False
            self.revision += 1

    def snapshot(self):
        with self._lock:
            self.refresh()
            tasks = [dict(task) for task in self.tasks.values()]
            history = [dict(event) for event in self.events if event["event"] == "enter"]
            steady_tasks = sum(task["is_steady"] for task in tasks)
            return {
                "simulation_id": self.simulation_id,
                "revision": self.revision,
                "is_monitoring": self.is_monitoring,
                "is_steady": steady_tasks > 0,
                "all_tasks_steady": bool(tasks) and steady_tasks == len(tasks),
                "steady_task_count": steady_tasks,
                "task_count": len(tasks),
                "steady_state_count": len(history),
                "history": history,
                "details": tasks,
                "execution": dict(self.execution_summary),
                "timestamp": time.time(),
                "message": f"当前稳态任务 {steady_tasks}/{len(tasks)}，累计进入稳态 {len(history)} 次",
            }

    def analysis(self):
        snapshot = self.snapshot()
        history = snapshot["history"]
        return {
            "file_found": bool(self.run_dir and self.run_dir.exists()),
            "steady_state_count": len(history),
            "steady_times_ns": [event["sim_time_ns"] for event in history],
            "steady_wall_times": history,
            "is_system_steady": bool(history),
            "task_summaries": snapshot["details"],
        }
