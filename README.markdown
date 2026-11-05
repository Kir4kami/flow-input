# Flow-Input

A tool for generating and processing network traffic patterns for NS-3 simulations.

>**Note**: Much more substantial information about ns-3 can be found at https://www.nsnam.org

This README excerpts some details from a more extensive tutorial that is maintained at: https://www.nsnam.org/documentation/latest/

## Prerequisites

Ensure the following are installed on your system:
- **Python 3**
- **gcc-9**
- **NS-3:3.39**

## Installation and Building NS-3

1. Configure and build NS-3:
   ```bash
   ./ns3 configure --enable-examples --enable-tests
   ./ns3
   ```

## Run Integrated Simulation (sim.sh)

To execute the complete simulation workflow with a single command:
```bash
cd examples/Reverie/
./sim.sh
```
>**Note**: This script will automatically handle all subsequent processes

## Traffic Generator

The traffic generator is located in `examples/Reverie/TrafficGenerator/`. It supports two types of input files: `deepseek` and `qwen`. The input file format is as follows:
- **First line**: Type of traffic and number of devices.
- **Subsequent lines**: Traffic details for each parallel strategy, with parameters:
  - `host_num`: Total number of nodes
  - `num_nodes`
  - `dp`
  - `msg_len`
  - `num_phases`: Used for TP
  - `num_iterations`: Used for TP
  - `device`: Device ID
  - `forward`: Forward or backward

### Running an Example

1. Navigate to the TrafficGenerator directory:
   ```bash
   cd examples/Reverie/TrafficGenerator/
   ```

2. Run the traffic generator with an input file:
   ```bash
   ./trafficGen.py --input_file deepseek.txt
   ```
   This generates an `rmda_result` folder.

3. Generate dependencies for the traffic file:
   ```bash
   ./merge_dependency.sh
   ```

4. Combine traffic files:
   ```bash
   ./merge_rdma.sh
   ```

5. The above steps generate a `task` folder, which serves as input for the main program.

## Running the Simulation

1. Navigate to the Reverie directory:
   ```bash
   cd examples/Reverie/
   ```

2. Run the simulation script:
   ```bash
   ./kira-parallel.sh
   ```

3. Results will be generated in `examples/Reverie/dump/`:
   - `evaluation.out`
   - `system1.log`

4. Hybrid Granularity Acceleration:

   Hybrid granularity is selected at runtime, without editing C++ sources:
   ```bash
   FLOW_INPUT_MIXED_GRANULARITY=1 ./sim.sh  # enabled (default)
   FLOW_INPUT_MIXED_GRANULARITY=0 ./sim.sh  # packet-level baseline
   ```
   The web UI passes this setting to every task. Both modes collect rate and
   steady-state statistics; only the enabled mode performs time transitions.

   Each run writes to `examples/Reverie/dump/runs/<run-id>/task<N>/`.
   `steady_events.jsonl` records entry/exit events with task ID, simulation time
   in nanoseconds, and the actual wall-clock timestamp. The API exposes task
   states and entry history through `/simulation-status`, `/steady-state-monitor`,
   and `/steady-state-history`. Short steady periods remain visible in history
   even when entry and exit occur between the two-second UI polls.

   Rate samples count payload and wire bytes separately over actual elapsed
   nanoseconds. Ten complete, fresh samples and stationary switch queues are
   required. A frozen per-flow plan advances whole payload packets, reserves
   in-flight data and a packet-level tail, and shifts pending events and pacer
   timestamps consistently. Window-limited or dynamic congestion-control
   flows and pending external releases defer acceleration. Every jump restarts
   sampling. This remains an approximation; verify accuracy against packet mode
   for each workload and protocol.

   `jump_events.jsonl` exposes the frozen plan and reasons for deferring a jump.
   `execution_metadata.json` includes native compute time and processed event
   count. The legacy `flow_SwitchStats.txt` remains an empty compatibility file;
   the current model does not consume or generate full switch-state matrices.

   Start the complete UI/API from the repository root:
   ```bash
   python3 examples/Reverie/api/start_complete_api.py
   # Open http://localhost:8000/complete_frontend.html
   ```
   After all tasks finish, aggregate compatibility files are written to `dump/`.
   `/flow_stats_txt?task_id=1` reads the selected task of the current run.

5. Network Topology Customization:

   Modify leaf-spine topology parameters in `examples/Reverie/generate_topology_leafspine.py`

6. Stage DAG execution:

   The web UI uses `api/dag_plan.py` and `api/dag_runner.py`. A communication
   stage is the minimum unit; all DAG predecessors, internal operation
   dependencies and phases are preserved. Every simulated unit starts in a
   fresh network. Representatives are calculated from frozen traffic and common
   network configuration. A generic labelled graph matcher checks dependencies,
   phase order, message sizes, priorities, QP relationships, physical resources,
   and data/ACK routes. Operator names do not determine equivalence. Explicit
   stage/operation/phase/flow/host/port mappings restore every original record.

   The built native simulator exports its exact routes and ordered next hops;
   each real job checks those against the frozen evidence. Missing or invalid
   evidence keeps ECMP inputs literal. Evidence binds the frozen inputs, network
   configuration, executable and loaded ns-3 libraries. Matching has a bounded
   search budget; an incomplete match keeps the unit independent.

   Order-changing graph matches are provisional. They require independent
   packet validation for this exact input before their results are accepted.
   A failed candidate falls back to the conservative partition and is recorded.
   Mixed mode validates nonliteral reuse separately, including operation/flow
   timing, steady events and transitions, because its sampling and jump ordering
   need not be invariant under renaming. Disabling validation excludes candidates
   that require it. Reported execution time includes the verification work.

   Representatives run in a configurable worker pool. The runner restores the
   original stage and flow timeline, detects overlapping stages that share
   network resources, and merges conflicting units until the partition is valid.
   Merged units preserve relative external release times. Mixed execution can
   trigger another refinement and packet validation cycle.

   The web workflow keeps necessary independent deduplication witnesses and
   local packet references, while deferring the complete packet baseline until
   the user clicks Analyze Results. Analysis runs one whole-DAG packet job with
   splitting, deduplication and mixed mode disabled, then automatically compares
   every flow's population, start, finish and FCT, operation and stage windows,
   and overall completion time. Matching successful baselines are reused across
   analyses and restarts using frozen traffic, dependencies, topology, protocol
   and native-runtime fingerprints. Failures and cancellation never publish a
   successful cache. Baseline work has separate state and directories and does
   not replace the live experiment's results or monitor. CLI/regression callers
   may still request the original three-way packet validation explicitly.
   Mixed results report their own errors and native compute speedup. Enabling mixed mode alone
   does not imply a transition occurred; short flows may finish before steady
   state. The UI shows actual representative events and mapped logical events
   separately, with provenance for reused events.

   `dump/runs/<run-id>/` stores `manifest.json`, frozen inputs, final `plan.json`,
   full `results.json`, independent references, deduplication validation/fallback
   evidence, and per-job telemetry including `native_routes.json`. The web
   path no longer uses the legacy fixed one/four-task shell workflow.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
## Regression tests

These tests require Python packages `pytest`, `fastapi`, `python-multipart`,
`httpx`, `networkx`, `matplotlib`, plus Node.js, Bash, and a C++ compiler (`g++`).

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest examples/Reverie/api/tests -p no:cacheprovider -q
node --test examples/Reverie/api/tests/frontend_monitor.test.cjs
```

The integration test runs the production API, shell launcher, and compiled C++
event writer with a small simulator stand-in. It validates one/four-task wiring,
output isolation, live monitoring, and failure propagation. It does not validate
ns-3 network behavior or acceleration accuracy; those require a Linux ns-3 build.
