#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NS3="$(cd "$SCRIPT_DIR/../.." && pwd)"
DUMP_DIR="$SCRIPT_DIR/dump"
TASKNUM="${1:-}"
if ! [[ "$TASKNUM" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: a positive task count is required" >&2
    exit 1
fi

# Every run and task owns its output, including while ns-3 is compiling.
RUN_DIR="${FLOW_INPUT_RUN_DIR:-$DUMP_DIR/runs/$(date +%s)-$$}"
mkdir -p "$RUN_DIR"
RUN_DIR="$(cd "$RUN_DIR" && pwd)"
END_TIME="${SIM_END_TIME_SEC_OVERRIDE:-${SIM_END_TIME_NS_OVERRIDE:-10000}}"
FLOW_LAUNCH_END_TIME="${SIM_FLOW_LAUNCH_END_SEC_OVERRIDE:-${SIM_FLOW_LAUNCH_END_NS_OVERRIDE:-3}}"
cd "$NS3"
./ns3 build sim -j "${NS3_BUILD_JOBS:-2}"

pids=()
trap 'for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done' TERM INT
for ((i=1; i<=TASKNUM; i++)); do
    task_dir="$RUN_DIR/task$i"
    mkdir -p "$task_dir"
    (
        export FLOW_INPUT_OUTPUT_DIR="$task_dir"
        export FLOW_INPUT_TASK_ID="$i"
        trap 'echo $? > "$FLOW_INPUT_OUTPUT_DIR/exit_code"' EXIT
        # Calibration input is copied before this task starts writing statistics.
        if [[ -f "$NS3/flow_SwitchStats.txt" ]]; then
            cp "$NS3/flow_SwitchStats.txt" "$task_dir/flow_SwitchStats.txt"
        fi
        ./ns3 run --no-build "sim --TASKINDEX=$i --DST=1 --START_TIME=0 --END_TIME=$END_TIME --FLOW_LAUNCH_END_TIME=$FLOW_LAUNCH_END_TIME --fctOutFile=evaluation.fct --torOutFile=evaluation.tor --pfcOutFile=evaluation.pfc"
    ) > "$task_dir/evaluation.out" 2>&1 &
    pids+=("$!")
done

# Publish compatibility files only after all children have finished.
status=0
for pid in "${pids[@]}"; do
    wait "$pid" || status=1
done
mkdir -p "$DUMP_DIR"
for name in evaluation.out flow_stats.txt evaluation.tor evaluation.pfc; do
    : > "$DUMP_DIR/$name"
    for ((i=1; i<=TASKNUM; i++)); do
        if [[ -f "$RUN_DIR/task$i/$name" ]]; then
            cat "$RUN_DIR/task$i/$name" >> "$DUMP_DIR/$name"
        fi
    done
done
: > "$DUMP_DIR/evaluation.fct1"
for ((i=1; i<=TASKNUM; i++)); do
    if [[ -f "$RUN_DIR/task$i/evaluation.fct$i" ]]; then
        cat "$RUN_DIR/task$i/evaluation.fct$i" >> "$DUMP_DIR/evaluation.fct1"
    fi
    if [[ -f "$RUN_DIR/task$i/system$i.log" ]]; then
        cp "$RUN_DIR/task$i/system$i.log" "$DUMP_DIR/system$i.log"
    fi
done
echo "Completed $TASKNUM tasks (status=$status)"
exit "$status"
