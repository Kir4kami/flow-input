#!/bin/bash

# 执行 sim.cc 的单任务脚本
# 输入目录：task1
# 任务索引：1

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 加载配置文件
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

# 重命名 rdma_operate.txt 为 rdma_operate0.txt（如果存在且未重命名）
if [ -f "task1/rdma_operate.txt" ] && [ ! -f "task1/rdma_operate0.txt" ]; then
    echo "重命名 rdma_operate.txt 为 rdma_operate0.txt..."
    mv "task1/rdma_operate.txt" "task1/rdma_operate0.txt" || {
        echo "错误: 无法重命名文件"
        exit 1
    }
fi

# 检查是否存在 rdma_operate 文件
if [ ! -f "task1/rdma_operate0.txt" ] && [ ! -f "task1/rdma_operate.txt" ]; then
    echo "警告: task1 目录中未找到 rdma_operate 文件"
fi

echo "=========================================="
echo "执行 sim.cc - 单任务模式"
echo "任务索引: 1"
echo "输入目录: task1"
echo "=========================================="

# 切换到 NS-3 根目录
cd "$NS3" || {
    echo "错误: 无法切换到 NS-3 目录: $NS3"
    exit 1
}

# 检查是否需要编译
if [ ! -f "build/scratch/sim-optimized" ] && [ ! -f "build/scratch/sim" ]; then
    echo "编译 sim..."
    ./ns3 build sim || {
        echo "错误: sim 编译失败"
        exit 1
    }
fi

# 创建 dump 目录（如果不存在）
DUMP_DIR="$SCRIPT_DIR/dump"
if [ ! -d "$DUMP_DIR" ]; then
    mkdir -p "$DUMP_DIR" || {
        echo "错误: 无法创建 dump 目录"
        exit 1
    }
fi

# 设置输出文件路径（注意：sim.cc 会在文件名后添加 taskIndex）
FCTFILE="$DUMP_DIR/task1.fct"
TORFILE="$DUMP_DIR/task1.tor"
DUMPFILE="$DUMP_DIR/task1.out"
PFCFILE="$DUMP_DIR/task1.pfc"

echo "输出文件:"
echo "  FCT: $FCTFILE"
echo "  TOR: $TORFILE"
echo "  PFC: $PFCFILE"
echo "  日志: $DUMPFILE"
echo ""

# 执行模拟
echo "开始执行模拟..."
time ./ns3 run "sim --TASKINDEX=1 --DST=1 --START_TIME=0 --END_TIME=10000 --FLOW_LAUNCH_END_TIME=3 --fctOutFile=$FCTFILE --torOutFile=$TORFILE --pfcOutFile=$PFCFILE" > "$DUMPFILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "模拟执行完成！"
    echo "结果文件保存在: $DUMP_DIR"
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "模拟执行失败，退出码: $EXIT_CODE"
    echo "请查看日志文件: $DUMPFILE"
    echo "=========================================="
    exit $EXIT_CODE
fi
