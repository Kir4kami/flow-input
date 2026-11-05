"""Exercise the actual C++ operation scheduler with a deterministic ns3 stub.

The integration suite runs the real ns3 binary. This small host-side check
isolates parser, dependency and callback behavior without requiring ns3 builds.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]

HARNESS = r'''
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <queue>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include "kira_functions.h"
#include "mixed-granularity.h"
namespace kira { std::ostream cout(std::cerr.rdbuf()); }
namespace ns3 {
template<class T> using Ptr = std::shared_ptr<T>;
struct Time {
    uint64_t value;
    uint64_t GetNanoSeconds() const { return value; }
    double GetSeconds() const { return value / 1e9; }
};
Time NanoSeconds(uint64_t value) { return {value}; }
struct OutputStreamWrapper {};
struct RdmaQueuePair {
    uint32_t sip, dip;
    uint16_t sport, dport;
    uint64_t m_size;
    Time startTime;
};
uint32_t ip_to_node_id(uint32_t id) { return id; }
struct Simulator {
    struct Event { uint64_t time, uid; std::function<void()> call; };
    struct Later {
        bool operator()(const Event& a, const Event& b) const {
            return a.time > b.time || (a.time == b.time && a.uid > b.uid);
        }
    };
    static uint64_t now, uid;
    static bool stopped;
    static std::priority_queue<Event, std::vector<Event>, Later> queue;
    static Time Now() { return {now}; }
    template<class F, class... A> static void Schedule(Time delay, F f, A... args) {
        queue.push({now + delay.value, ++uid, std::bind(f, args...)});
    }
    template<class F, class... A> static void ScheduleNow(F f, A... args) {
        Schedule(NanoSeconds(0), f, args...);
    }
    static void Stop() { stopped = true; }
    static void Run() {
        while (!stopped && !queue.empty()) {
            Event event = queue.top(); queue.pop(); now = event.time; event.call();
        }
    }
};
uint64_t Simulator::now = 0, Simulator::uid = 0;
bool Simulator::stopped = false;
std::priority_queue<Simulator::Event, std::vector<Simulator::Event>, Simulator::Later> Simulator::queue;
}
using namespace ns3;
using namespace std;
vector<uint32_t> serverAddress(8);
__GLOBALS__
void flowinput_cb(Ptr<OutputStreamWrapper> fout, Ptr<RdmaQueuePair> q);
void flowSend(FlowInfo& flow) {
    auto q = std::make_shared<RdmaQueuePair>();
    q->sip = flow.src_node; q->dip = flow.dst_node;
    q->sport = flow.src_port; q->dport = flow.dst_port;
    q->m_size = flow.msg_len; q->startTime = Simulator::Now();
    Simulator::Schedule(NanoSeconds(flow.msg_len), flowinput_cb,
                        Ptr<OutputStreamWrapper>{}, q);
}
__SCHEDULER__
__PARSER__
int main(int argc, char** argv) {
    try {
        if (std::string(argv[1]) == "--guard") {
            SetPendingExternalReleases({0, 100, 100});
            if (!HasPendingExternalReleases()) return 3;
            MarkExternalReleaseProcessed(0);
            if (!HasPendingExternalReleases()) return 4;
            MarkExternalReleaseProcessed(100);
            if (HasPendingExternalReleases()) return 5;
            RegisterUnobservedFlow("0-1-1000-1000");
            if (!HasUnobservedFlows()) return 6;
            MarkFlowObserved("0-1-1000-1000");
            if (HasUnobservedFlows()) return 7;
            return 0;
        }
        taskInputDir = workFolder = argv[1]; operateNum = std::stoul(argv[2]);
        long count = 0;
        workload_rdma(count, 8, 1, 0, 0, 0);
        Simulator::Run();
        if (completedOperations != operateNum) throw std::runtime_error("scheduler deadlocked");
        std::cout << "{\"completed\":" << completedOperations
                  << ",\"finish_ns\":" << Simulator::Now().GetNanoSeconds() << "}";
    } catch (const std::exception& error) {
        std::cerr << error.what() << std::endl;
        return 2;
    }
}
'''


def rdma(size=10, port=1000):
    return (f"Type rdma_send src_node 0 src_port {port} dst_node 1 "
            f"dst_port {port} priority 0 msg_len {size}\n")


class OperationEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if compiler is None and Path("D:/MinGW/bin/g++.exe").is_file():
            compiler = "D:/MinGW/bin/g++.exe"
        if compiler is None:
            raise unittest.SkipTest("C++ host compiler unavailable")
        cls.build_dir = tempfile.TemporaryDirectory(prefix="flow-operation-engine-")
        cls.addClassCleanup(cls.build_dir.cleanup)
        source = (ROOT / "examples/Reverie/sim.cc").read_text(encoding="utf-8")
        sections = {
            "__GLOBALS__": source.split('std::string workFolder =', 1)[1].split('//MPI_Datatype', 1)[0],
            "__SCHEDULER__": source.split('void sendPhase(size_t operation) {', 1)[1].split('uint16_t DST;', 1)[0],
            "__PARSER__": source.split('uint64_t ParseUnsigned(', 1)[1].split('//written by Kira END', 1)[0],
        }
        sections["__GLOBALS__"] = 'std::string workFolder =' + sections["__GLOBALS__"]
        sections["__SCHEDULER__"] = 'void sendPhase(size_t operation) {' + sections["__SCHEDULER__"]
        sections["__PARSER__"] = 'uint64_t ParseUnsigned(' + sections["__PARSER__"]
        harness = HARNESS
        for marker, text in sections.items():
            harness = harness.replace(marker, text)
        source_file = Path(cls.build_dir.name) / "operation-engine.cc"
        source_file.write_text(harness, encoding="utf-8")
        cls.binary = source_file.with_suffix(".exe" if os.name == "nt" else "")
        subprocess.run([
            compiler, "-std=c++17", "-iquote", str(ROOT / "examples/Reverie"),
            "-iquote", str(ROOT / "src/core/model"), str(source_file),
            str(ROOT / "src/core/model/mixed-granularity.cc"), "-o", str(cls.binary),
        ], check=True, capture_output=True, text=True)

    def execute(self, operations, dependencies="", releases="", missing=()):
        with tempfile.TemporaryDirectory(prefix="flow-operation-input-") as temp:
            path = Path(temp)
            for index, operation in enumerate(operations):
                if index not in missing:
                    (path / f"rdma_operate{index}.txt").write_text(operation, encoding="utf-8")
            (path / "dependence.txt").write_text(dependencies, encoding="utf-8")
            (path / "release_times.txt").write_text(releases, encoding="utf-8")
            env = dict(os.environ, FLOW_INPUT_OUTPUT_DIR=str(path))
            result = subprocess.run([str(self.binary), temp, str(len(operations))],
                                    capture_output=True, text=True, env=env)
            records = {}
            for kind in ("flow", "operation"):
                file = path / f"{kind}_events.jsonl"
                records[kind] = [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []
            return result, records

    def test_multiple_parents_release_and_empty_phases(self):
        result, records = self.execute([
            "phase:0\n" + rdma(10), "phase:0\nphase:1\n",
            "phase:0\n" + rdma(20) + "phase:1\nphase:2\n" + rdma(30),
        ], "2:0\n2:1\n", "1 5\n2 50\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"completed": 3, "finish_ns": 100})
        completions = {e["operation_index"]: e for e in records["operation"] if e["event"] == "operation_complete"}
        self.assertEqual([(completions[i]["start_ns"], completions[i]["finish_ns"]) for i in range(3)],
                         [(0, 10), (5, 5), (50, 100)])
        self.assertEqual([(e["phase_index"], e["start_ns"], e["finish_ns"], e["fct_ns"])
                          for e in records["flow"]], [(0, 0, 10, 10), (0, 50, 70, 20), (2, 70, 100, 30)])

    def test_more_than_255_empty_operations(self):
        result, records = self.execute([""] * 300, "".join(f"{i}:{i - 1}\n" for i in range(1, 300)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"completed": 300, "finish_ns": 0})
        self.assertEqual(sum(e["event"] == "operation_complete" for e in records["operation"]), 300)

    def test_bad_inputs_fail_instead_of_hanging(self):
        for operations, dependency, releases, missing, expected in [
            (["", ""], "0:1\n1:0\n", "", (), "cycle"),
            ([""], "0:0\n", "", (), "itself"),
            ([""], "0:2\n", "", (), "outside"),
            ([rdma()], "", "", (), "precedes"),
            ([""], "", "", (0,), "Missing traffic"),
            ([""], "", "0 -1\n", (), "Invalid unsigned"),
            (["phase:0\n" + rdma() + rdma()], "", "", (), "reuse"),
        ]:
            with self.subTest(expected=expected):
                result, _ = self.execute(operations, dependency, releases, missing)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)

    def test_mixed_guard_waits_for_actual_release_callback(self):
        result = subprocess.run([str(self.binary), "--guard"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
