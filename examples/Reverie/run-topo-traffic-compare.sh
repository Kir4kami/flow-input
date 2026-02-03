#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

LIST_FILE="${1:-$SCRIPT_DIR/topology_list.txt}"
TOPO_GEN="$SCRIPT_DIR/generate_topology_leafspine_param.py"
TRAFFIC_GEN="$SCRIPT_DIR/TrafficGenerator/DP_onephase.py"

if [ ! -f "$LIST_FILE" ]; then
    echo "错误: 拓扑列表文件不存在: $LIST_FILE"
    exit 1
fi

if [ ! -f "$TOPO_GEN" ]; then
    echo "错误: 拓扑生成脚本不存在: $TOPO_GEN"
    exit 1
fi

if [ ! -f "$TRAFFIC_GEN" ]; then
    echo "错误: 流量生成脚本不存在: $TRAFFIC_GEN"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/config.sh" ]; then
    echo "错误: config.sh 不存在: $SCRIPT_DIR/config.sh"
    exit 1
fi

ensure_task1() {
    if [ ! -d "$SCRIPT_DIR/task1" ]; then
        mkdir -p "$SCRIPT_DIR/task1"
    fi
}

run_simulation() {
    local mode="$1"   # numerical / original
    local outdir="$2"
    local program="$3"
    local build_target="$4"

    # 记录运行前已有 results_ 时间戳目录（用于归档新生成的目录）
    local before_file
    before_file="$(mktemp)"
    if [ -d "$NS3" ]; then
        find "$NS3" -maxdepth 1 -type d -name 'results_*' -print0 | tr '\0' '\n' > "$before_file"
    else
        : > "$before_file"
    fi

    cd "$NS3" || exit 1

    # 编译（如需要）
    if [ ! -f "build/scratch/${build_target}-optimized" ] && [ ! -f "build/scratch/${build_target}" ]; then
        echo "编译 ${build_target}..."
        ./ns3 build "${build_target}"
    fi

    # 输出文件
    local fctfile="${outdir}/task1.fct"
    local torfile="${outdir}/task1.tor"
    local pfcfile="${outdir}/task1.pfc"
    local outfile="${outdir}/task1.out"

    echo "=========================================="
    echo "执行 ${program} (${mode})"
    echo "输出目录: ${outdir}"
    echo "=========================================="

    local cmd="time ./ns3 run \"${program} --TASKINDEX=${TASKINDEX} --DST=${DST} --START_TIME=${START_TIME} --END_TIME=${END_TIME} --FLOW_LAUNCH_END_TIME=${FLOW_LAUNCH_END_TIME} --fctOutFile=${fctfile} --torOutFile=${torfile} --pfcOutFile=${pfcfile}\""
    if [ -n "${BUFFERSIZE}" ]; then
        cmd="time ./ns3 run \"${program} --TASKINDEX=${TASKINDEX} --DST=${DST} --START_TIME=${START_TIME} --END_TIME=${END_TIME} --FLOW_LAUNCH_END_TIME=${FLOW_LAUNCH_END_TIME} --buffersize=${BUFFERSIZE} --fctOutFile=${fctfile} --torOutFile=${torfile} --pfcOutFile=${pfcfile}\""
    fi

    # 运行
    echo "命令: ${cmd}"
    bash -lc "${cmd}" > "${outfile}" 2>&1

    # 收集并移动新生成的 results_ 时间戳目录内容（只保留文件，不保留目录）
    local results_archive_dir="${outdir}/results_timestamped"
    mkdir -p "$results_archive_dir"
    if [ -d "$NS3" ]; then
        while IFS= read -r -d '' dir; do
            if ! grep -F -x -q "$dir" "$before_file"; then
                if [ -d "$dir" ]; then
                    find "$dir" -maxdepth 1 -type f -exec mv -t "$results_archive_dir" {} +
                    rmdir "$dir" 2>/dev/null || true
                fi
            fi
        done < <(find "$NS3" -maxdepth 1 -type d -name 'results_*' -print0)
    fi
    rm -f "$before_file"

    # 从输出提取仿真时间，生成 system1.log（用于加速比计算）
    if grep -q "simulation time:" "${outfile}"; then
        grep -E "total time:|simulation time:" "${outfile}" > "${outdir}/system1.log"
    else
        # 回退：尝试从默认位置拷贝
        if [ -f "${SCRIPT_DIR}/dump/system1.log" ]; then
            cp "${SCRIPT_DIR}/dump/system1.log" "${outdir}/system1.log"
        elif [ -f "${NS3}/system1.log" ]; then
            cp "${NS3}/system1.log" "${outdir}/system1.log"
        fi
    fi
}

echo "使用拓扑列表: $LIST_FILE"

while read -r line; do
    # 跳过空行和注释
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    # 解析字段
    read -r label serversPerTor torSwitches spineSwitches serverTorDelay torSpineDelay serverDataRate otherDataRate errorRate msgLen <<< "$line"

    if [ -z "${label:-}" ]; then
        continue
    fi

    echo "=========================================="
    echo "拓扑: $label"
    echo "serversPerTor=$serversPerTor torSwitches=$torSwitches spineSwitches=$spineSwitches"
    echo "serverTorDelay=$serverTorDelay torSpineDelay=$torSpineDelay"
    echo "serverDataRate=$serverDataRate otherDataRate=$otherDataRate errorRate=$errorRate"
    echo "msgLen=$msgLen"
    echo "=========================================="

    # 生成拓扑文件
    python3 "$TOPO_GEN" \
        --servers_per_tor "$serversPerTor" \
        --tor_switches "$torSwitches" \
        --spine_switches "$spineSwitches" \
        --server_tor_delay "$serverTorDelay" \
        --tor_spine_delay "$torSpineDelay" \
        --server_data_rate "$serverDataRate" \
        --other_data_rate "$otherDataRate" \
        --error_rate "$errorRate" \
        --output_file "$SCRIPT_DIR/leaf-spine.txt"

    # 生成 DP 流量（task1 中包含所有 rdma_operate*.txt）
    ensure_task1
    totalNodes=$((serversPerTor * torSwitches))
    DP_LIST="${DP_LIST:-8}"
    TRAFFIC_OUT_DIR="$SCRIPT_DIR/TrafficGenerator/result"
    rm -rf "$TRAFFIC_OUT_DIR"
    python3 "$TRAFFIC_GEN" \
        --host_num "$totalNodes" \
        --dp_list "$DP_LIST" \
        --msg_len "$msgLen" \
        --output_dir "$TRAFFIC_OUT_DIR" \
        --topo "topo_dp"
    rm -f "$SCRIPT_DIR/task1/rdma_operate"*.txt
    find "$TRAFFIC_OUT_DIR/topo_dp/host_num${totalNodes}" -type f -name 'rdma_operate*.txt' -exec cp {} "$SCRIPT_DIR/task1/" \;

    # 直接输出到最终目录
    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    RESULT_ROOT="$SCRIPT_DIR/results_topology_${label}/results_compare_${TIMESTAMP}"
    NUM_DIR="$RESULT_ROOT/numerical"
    ORG_DIR="$RESULT_ROOT/original"
    mkdir -p "$NUM_DIR" "$ORG_DIR"

    # 加载 config.sh，获得 NS3
    source "$SCRIPT_DIR/config.sh"

    # 可选参数
    TASKINDEX="${TASKINDEX:-1}"
    START_TIME="${START_TIME:-0}"
    END_TIME="${END_TIME:-10000}"
    FLOW_LAUNCH_END_TIME="${FLOW_LAUNCH_END_TIME:-3}"
    DST="${DST:-1}"
    BUFFERSIZE="${BUFFERSIZE:-}"

    run_simulation "numerical" "$NUM_DIR" "sim" "sim"
    run_simulation "original" "$ORG_DIR" "reverie-evaluation-sigcomm2023" "reverie-evaluation-sigcomm2023"

    # 计算保真度和加速比
    REPORT_FILE="$RESULT_ROOT/comparison_report.txt"
    python3 "$SCRIPT_DIR/calculate_fidelity_speedup.py" "$ORG_DIR" "$NUM_DIR" | tee "$REPORT_FILE"

    # 写入拓扑与流量文件
    cp "$SCRIPT_DIR/leaf-spine.txt" "$RESULT_ROOT/leaf-spine.txt"
    find "$SCRIPT_DIR/task1" -type f -name 'rdma_operate*.txt' -exec cp {} "$RESULT_ROOT/" \;

    echo "结果已输出: $RESULT_ROOT"

done < "$LIST_FILE"
