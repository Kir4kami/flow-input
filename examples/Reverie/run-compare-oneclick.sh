#!/bin/bash
set -euo pipefail

# 一键运行数值仿真(sim.cc)与原始仿真(reverie-evaluation-sigcomm2023.cc)，
# 并输出加速比与保真度对比结果。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
TOPO_GEN="$SCRIPT_DIR/generate_topology_leafspine_param.py"

# 加载配置
if [ -f "config.sh" ]; then
    source config.sh
else
    echo "错误: 找不到 config.sh 文件"
    exit 1
fi

if [ ! -f "$TOPO_GEN" ]; then
    echo "错误: 找不到拓扑生成脚本: $TOPO_GEN"
    exit 1
fi

ensure_task1() {
    if [ ! -d "task1" ]; then
        mkdir -p "task1"
    fi
}

generate_traffic_for_mode() {
    local mode="$1"
    local totalNodes="$2"
    local msgLen="$3"
    local trafficOutDir="$4"
    local topoTag="$5"
    local dpList="${DP_LIST:-8}"

    case "$mode" in
        dp|DP)
            python3 "$SCRIPT_DIR/TrafficGenerator/DP_onephase.py" \
                --host_num "$totalNodes" \
                --dp_list "$dpList" \
                --msg_len "$msgLen" \
                --output_dir "$trafficOutDir" \
                --topo "$topoTag"
            ;;
        ep|EP)
            python3 "$SCRIPT_DIR/TrafficGenerator/EP.py" \
                --host_num "$totalNodes" \
                --dp_list "$dpList" \
                --msg_len "$msgLen" \
                --output_dir "$trafficOutDir" \
                --topo "$topoTag"
            ;;
        pp|PP)
            python3 "$SCRIPT_DIR/TrafficGenerator/PP.py" \
                --host_num "$totalNodes" \
                --dp_list "$dpList" \
                --msg_len "$msgLen" \
                --output_dir "$trafficOutDir" \
                --topo "$topoTag"
            ;;
        tp|TP)
            python3 "$SCRIPT_DIR/TrafficGenerator/TP_ring.py" \
                --total_nodes "$totalNodes" \
                --msg_len "$msgLen" \
                --output_dir "$trafficOutDir" \
                --topo "$topoTag"
            ;;
        *)
            echo "错误: 不支持的流量模式 '$mode'，仅支持 dp/ep/pp/tp"
            exit 1
            ;;
    esac
}

# 默认：直接使用现有 task1（不自动从 topology_list 生成流量）
USE_TOPOLOGY_LIST_TRAFFIC="${USE_TOPOLOGY_LIST_TRAFFIC:-0}"
TOPOLOGY_LIST_FILE="${TOPOLOGY_LIST_FILE:-$SCRIPT_DIR/topology_list.txt}"
if [ "$USE_TOPOLOGY_LIST_TRAFFIC" = "1" ]; then
    if [ ! -f "$TOPOLOGY_LIST_FILE" ]; then
        echo "错误: USE_TOPOLOGY_LIST_TRAFFIC=1 但未找到 topology_list 文件: $TOPOLOGY_LIST_FILE"
        exit 1
    fi
    first_line="$(grep -vE '^\s*#|^\s*$' "$TOPOLOGY_LIST_FILE" | head -n 1 || true)"
    if [ -z "$first_line" ]; then
        echo "错误: topology_list 文件没有可用配置行: $TOPOLOGY_LIST_FILE"
        exit 1
    fi
    read -r label serversPerTor torSwitches spineSwitches serverTorDelay torSpineDelay serverDataRate otherDataRate errorRate msgLen trafficMode <<< "$first_line"
    trafficMode="${TRAFFIC_MODE:-${trafficMode:-dp}}"
    totalNodes=$((serversPerTor * torSwitches))

    # 根据 topology_list 生成 leaf-spine.txt，确保 run-compare 可直接运行
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

    TRAFFIC_OUT_DIR="$SCRIPT_DIR/TrafficGenerator/result"
    TOPO_TAG="topo_${trafficMode,,}"
    rm -rf "$TRAFFIC_OUT_DIR"
    generate_traffic_for_mode "$trafficMode" "$totalNodes" "$msgLen" "$TRAFFIC_OUT_DIR" "$TOPO_TAG"
    ensure_task1
    rm -f "$SCRIPT_DIR/task1/rdma_operate"*.txt
    find "$TRAFFIC_OUT_DIR/$TOPO_TAG/host_num${totalNodes}" -type f -name 'rdma_operate*.txt' -exec cp {} "$SCRIPT_DIR/task1/" \;
fi

# 检查 task1 目录是否存在
if [ ! -d "task1" ]; then
    echo "错误: task1 目录不存在！"
    echo "请先运行 sim.sh 生成 task1 目录，或保持 USE_TOPOLOGY_LIST_TRAFFIC=1 自动生成"
    exit 1
fi

# 重命名 rdma_operate.txt 为 rdma_operate0.txt（若需要）
if [ -f "task1/rdma_operate.txt" ] && [ ! -f "task1/rdma_operate0.txt" ]; then
    mv "task1/rdma_operate.txt" "task1/rdma_operate0.txt"
fi

# 可选参数
TASKINDEX="${TASKINDEX:-1}"
START_TIME="${START_TIME:-0}"
END_TIME="${END_TIME:-10000}"
FLOW_LAUNCH_END_TIME="${FLOW_LAUNCH_END_TIME:-3}"
DST="${DST:-1}"
BUFFERSIZE="${BUFFERSIZE:-}"
ENABLE_FCT_LOGICAL_TRACE="${ENABLE_FCT_LOGICAL_TRACE:-}"

# 结果目录
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RESULT_ROOT="$SCRIPT_DIR/results_compare_$TIMESTAMP"
NUM_DIR="$RESULT_ROOT/numerical"
ORG_DIR="$RESULT_ROOT/original"
mkdir -p "$NUM_DIR" "$ORG_DIR"

run_simulation() {
    local mode="$1"   # numerical / original
    local outdir="$2"
    local program="$3"
    local build_target="$4"
    local results_archive_dir="${outdir}/results_timestamped"
    mkdir -p "$results_archive_dir"

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

    local traceArg=""
    if [ -n "${ENABLE_FCT_LOGICAL_TRACE}" ]; then
        traceArg=" --enableFctLogicalTrace=${ENABLE_FCT_LOGICAL_TRACE}"
    fi

    local cmd="time ./ns3 run \"${program} --TASKINDEX=${TASKINDEX} --DST=${DST} --START_TIME=${START_TIME} --END_TIME=${END_TIME} --FLOW_LAUNCH_END_TIME=${FLOW_LAUNCH_END_TIME} --fctOutFile=${fctfile} --torOutFile=${torfile} --pfcOutFile=${pfcfile}${traceArg}\""
    if [ -n "${BUFFERSIZE}" ]; then
        cmd="time ./ns3 run \"${program} --TASKINDEX=${TASKINDEX} --DST=${DST} --START_TIME=${START_TIME} --END_TIME=${END_TIME} --FLOW_LAUNCH_END_TIME=${FLOW_LAUNCH_END_TIME} --buffersize=${BUFFERSIZE} --fctOutFile=${fctfile} --torOutFile=${torfile} --pfcOutFile=${pfcfile}${traceArg}\""
    fi

    # 运行：统计类输出直接写入本次结果目录（一步到位，不再中转搬运）
    echo "命令: NS3_OUTPUT_DIRECTORY=${results_archive_dir} ${cmd}"
    NS3_OUTPUT_DIRECTORY="${results_archive_dir}" bash -lc "${cmd}" > "${outfile}" 2>&1

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

# 执行数值仿真
run_simulation "numerical" "$NUM_DIR" "sim" "sim"

# 执行原始仿真
run_simulation "original" "$ORG_DIR" "reverie-evaluation-sigcomm2023" "reverie-evaluation-sigcomm2023"

# 计算保真度和加速比
cd "$SCRIPT_DIR" || exit 1
REPORT_FILE="$RESULT_ROOT/comparison_report.txt"
python3 "$SCRIPT_DIR/calculate_fidelity_speedup.py" "$ORG_DIR" "$NUM_DIR" | tee "$REPORT_FILE"

echo ""
echo "对比完成，结果输出："
echo "  结果目录: $RESULT_ROOT"
echo "  报告文件: $REPORT_FILE"
