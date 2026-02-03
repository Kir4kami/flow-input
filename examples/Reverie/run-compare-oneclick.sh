#!/bin/bash
set -euo pipefail

# 一键运行数值仿真(sim.cc)与原始仿真(reverie-evaluation-sigcomm2023.cc)，
# 并输出加速比与保真度对比结果。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 加载配置
if [ -f "config.sh" ]; then
    source config.sh
else
    echo "错误: 找不到 config.sh 文件"
    exit 1
fi

# 检查 task1 目录是否存在
if [ ! -d "task1" ]; then
    echo "错误: task1 目录不存在！"
    echo "请先运行 sim.sh 生成 task1 目录"
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
