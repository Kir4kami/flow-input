import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dag_routes


def fixture():
    flow = dict(src=0, dst=1, sport=1000, dport=1000, priority=0, msg_len=32768)
    plan = dict(experiment_fingerprint="frozen-experiment",
                topology={"nodes": [{"id": i, "role": "leaf" if i == 2 else "host"} for i in range(3)],
                          "links": [{"src": 0, "dst": 2}, {"src": 1, "dst": 2}]},
                topology_text="3 1 1 2 25000000000 25000000000\n2\n0 2 25000000000 2us 0\n1 2 25000000000 2us 0\n",
                config_text="PACKET_PAYLOAD_SIZE 1000\n",
                stages=[{"operations": [{"phases": [[flow]]}]}])
    def hop(node, out_if, peer, in_if, switch=False):
        value = dict(node=node, out_if=out_if, next_node=peer, in_if=in_if,
                     next_hop_out_ifs=[out_if],
                     hash_algorithm="SwitchNode::EcmpHash" if switch else "ns3::Hash32")
        if switch:
            value["ecmp_seed"] = node
        return value
    data = dict(schema_version=1, oracle="native", certified=True,
                protocol_coverage={"data": [17], "reverse": [252, 253]},
                routes={"0,1,1000,1000": {
                    "forward": [0, 2, 1], "reverse": [1, 2, 0],
                    "forward_hops": [hop(0, 1, 2, 1), hop(2, 2, 1, 1, True)],
                    "reverse_hops": [hop(1, 1, 2, 2), hop(2, 1, 0, 1, True)]}})
    return plan, data


class NativeRoutesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dag-routes-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "native-sim"
        self.binary.write_bytes(b"test-native-binary")
        self.plan, self.data = fixture()
        self.posix = SimpleNamespace(name="posix", environ=os.environ, pathsep=os.pathsep)

    def collect(self, run):
        with patch.object(dag_routes, "os", self.posix), \
             patch.object(dag_routes, "_native_binary", return_value=self.binary), \
             patch.object(dag_routes.subprocess, "run", side_effect=run):
            return dag_routes.collect_plan_routes(self.plan, self.root, self.root / "review")

    def test_native_route_collection_freezes_inputs_without_changing_plan(self):
        original = copy.deepcopy(self.plan)
        def run(command, **kwargs):
            self.assertEqual(command[0], str(self.binary))
            self.assertTrue(kwargs["capture_output"])
            self.assertFalse(kwargs["check"])
            output = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--exportRoutesOnly=")))
            output.write_text(json.dumps(self.data), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "native oracle only", "")
        result = self.collect(run)
        self.assertEqual(self.plan, original)
        certificate = result["route_certificate"]
        self.assertTrue(certificate["certified"])
        self.assertEqual(certificate["experiment_fingerprint"], self.plan["experiment_fingerprint"])
        self.assertEqual(certificate["routes"], self.data["routes"])
        directory = Path(certificate["oracle_directory"])
        self.assertEqual((directory / "topology.txt").read_text(), self.plan["topology_text"])
        self.assertEqual((directory / "config-workload.txt").read_text(), self.plan["config_text"])
        self.assertTrue((directory / "certificate.json").is_file())

    def test_missing_binary_is_conservative_and_does_not_build(self):
        with patch.object(dag_routes, "os", self.posix), \
             patch.object(dag_routes, "_native_binary", return_value=None), \
             patch.object(dag_routes.subprocess, "run") as run:
            result = dag_routes.collect_plan_routes(self.plan, self.root)
        self.assertFalse(result["route_certificate"]["certified"])
        self.assertIn("no build was attempted", result["route_certificate"]["reason"])
        run.assert_not_called()

    def test_failed_oracle_is_explicitly_unavailable(self):
        for code, payload, expected in [(7, None, "exited 7"),
                                        (0, {}, "certified v1"),
                                        (0, dict(self.data, routes={}), "population")]:
            def run(command, **kwargs):
                if payload is not None:
                    output = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--exportRoutesOnly=")))
                    output.write_text(json.dumps(payload), encoding="utf-8")
                return subprocess.CompletedProcess(command, code, "", "diagnostic")
            with self.subTest(expected=expected):
                result = self.collect(run)
                self.assertFalse(result["route_certificate"]["certified"])
                self.assertIn(expected, result["route_certificate"]["reason"])

    def test_rejects_fake_physical_paths_or_next_hop_evidence(self):
        for mutation in ("physical", "candidate", "seed", "protocol"):
            data = copy.deepcopy(self.data)
            route = data["routes"]["0,1,1000,1000"]
            if mutation == "physical":
                route["reverse_hops"][0]["in_if"] = 3
            elif mutation == "candidate":
                route["forward_hops"][0]["next_hop_out_ifs"] = [99]
            elif mutation == "seed":
                del route["forward_hops"][1]["ecmp_seed"]
            else:
                data["protocol_coverage"]["reverse"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                dag_routes.validate_native_routes(data, dag_routes._flows(self.plan), self.plan["topology"])

    def test_timeout_is_reported_without_a_certificate(self):
        result = self.collect(lambda command, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(command, 1)))
        self.assertFalse(result["route_certificate"]["certified"])
        self.assertIn("TimeoutExpired", result["route_certificate"]["reason"])

    def test_runtime_fingerprint_changes_when_only_shared_library_changes(self):
        library = self.root / "build/lib/libns3.39-point-to-point-debug.so"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"routing implementation one")
        first = dag_routes._runtime_fingerprint(self.binary, self.root)
        library.write_bytes(b"routing implementation two")
        second = dag_routes._runtime_fingerprint(self.binary, self.root)
        self.assertEqual(first["native_binary_sha256"], second["native_binary_sha256"])
        self.assertNotEqual(first["native_runtime_sha256"], second["native_runtime_sha256"])

    def test_binary_discovery_uses_configured_profile_and_rejects_ambiguity(self):
        directory = self.root / "build/examples/Reverie"
        directory.mkdir(parents=True)
        for profile in ("debug", "optimized"):
            binary = directory / f"ns3.39-sim-{profile}"
            binary.write_bytes(b"native executable")
            binary.chmod(0o755)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(dag_routes._native_binary(self.root))
            (self.root / ".lock-ns3_linux_build").write_text(
                "ns3_runnable_programs = ['/other/build/examples/Reverie/ns3.39-sim-optimized']\n")
            self.assertEqual(dag_routes._native_binary(self.root).name, "ns3.39-sim-optimized")


if __name__ == "__main__":
    unittest.main()
