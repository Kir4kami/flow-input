#!/bin/bash

# 运行主机对流仿真脚本
# 使用 task1/rdma_operate0.txt 进行仿真测试

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "运行主机对流仿真测试"
echo "=========================================="

# 1. 检查输入文件
echo ""
echo "步骤1: 检查输入文件..."
TASK_DIR="task1"
INPUT_FILE="$TASK_DIR/rdma_operate0.txt"

if [ ! -f "$INPUT_FILE" ]; then
    echo "错误: 找不到输入文件 $INPUT_FILE"
    exit 1
fi

echo "✓ 找到输入文件: $INPUT_FILE"
echo "流数量: $(grep -c "Type rdma_send" "$INPUT_FILE")"

# 检查 dependence.txt
if [ ! -f "$TASK_DIR/dependence.txt" ]; then
    echo "# auto-generated: no explicit operate dependencies" > "$TASK_DIR/dependence.txt"
    echo "✓ 创建空的 dependence.txt"
fi

# 2. 清理旧的输出文件
echo ""
echo "步骤2: 清理旧的输出文件..."
rm -f ../flow_stats.txt
rm -f flow_stats.txt
rm -f dump/evaluation.out dump/evaluation.fct* dump/evaluation.tor dump/evaluation.pfc
echo "✓ 已清理旧文件"

# 3. 加载配置
echo ""
echo "步骤3: 加载配置..."
if [ ! -f "config.sh" ]; then
    echo "错误: 找不到 config.sh"
    exit 1
fi
source config.sh
echo "✓ NS3 路径: $NS3"

# 4. 检查编译
echo ""
echo "步骤4: 检查编译..."
cd $NS3
if [ ! -f "build/ns3" ]; then
    echo "正在编译 NS-3..."
    ./ns3 build
    if [ $? -ne 0 ]; then
        echo "错误: 编译失败"
        exit 1
    fi
else
    echo "✓ NS-3 已编译"
fi

# 5. 运行仿真
echo ""
echo "步骤5: 运行仿真..."
echo "使用文件: examples/Reverie/$INPUT_FILE"
echo "输出文件: flow_stats.txt"
echo ""

# 设置仿真参数
TASKINDEX=1
DST=1
START_TIME=0
END_TIME=100000  # 100秒仿真时间
FLOW_LAUNCH_END_TIME=3

# 运行仿真
echo "执行命令:"
echo "  ./ns3 run \"reverie-evaluation-sigcomm2023 --TASKINDEX=$TASKINDEX --DST=$DST --START_TIME=$START_TIME --END_TIME=$END_TIME --FLOW_LAUNCH_END_TIME=$FLOW_LAUNCH_END_TIME\""
echo ""
echo "开始运行（这可能需要一些时间）..."
echo ""

./ns3 run "reverie-evaluation-sigcomm2023 --TASKINDEX=$TASKINDEX --DST=$DST --START_TIME=$START_TIME --END_TIME=$END_TIME --FLOW_LAUNCH_END_TIME=$FLOW_LAUNCH_END_TIME" > examples/Reverie/dump/evaluation.out 2>&1

SIM_EXIT_CODE=$?

# 6. 检查结果
echo ""
echo "=========================================="
if [ $SIM_EXIT_CODE -eq 0 ]; then
    echo "仿真完成！"
else
    echo "仿真可能出错（退出码: $SIM_EXIT_CODE）"
fi
echo "=========================================="

# 检查 flow_stats.txt 的位置
FLOW_STATS_FILE=""
if [ -f "$NS3/flow_stats.txt" ]; then
    FLOW_STATS_FILE="$NS3/flow_stats.txt"
    echo ""
    echo "✓ 成功生成 flow_stats.txt"
    echo "文件位置: $FLOW_STATS_FILE"
    echo ""
    echo "文件内容预览（最后30行）:"
    echo "----------------------------------------"
    tail -30 "$FLOW_STATS_FILE"
    echo "----------------------------------------"
    echo ""
    echo "总记录数: $(grep -c "Flow ID:" "$FLOW_STATS_FILE" 2>/dev/null || echo "0")"
elif [ -f "examples/Reverie/flow_stats.txt" ]; then
    FLOW_STATS_FILE="examples/Reverie/flow_stats.txt"
    echo ""
    echo "✓ 成功生成 flow_stats.txt"
    echo "文件位置: $FLOW_STATS_FILE"
    echo ""
    echo "文件内容预览（最后30行）:"
    echo "----------------------------------------"
    tail -30 "$FLOW_STATS_FILE"
    echo "----------------------------------------"
    echo ""
    echo "总记录数: $(grep -c "Flow ID:" "$FLOW_STATS_FILE" 2>/dev/null || echo "0")"
else
    echo ""
    echo "⚠ 警告: flow_stats.txt 未生成"
    echo "请检查 dump/evaluation.out 查看错误信息"
    if [ -f "examples/Reverie/dump/evaluation.out" ]; then
        echo ""
        echo "错误日志（最后50行）:"
        tail -50 examples/Reverie/dump/evaluation.out
    fi
fi

echo ""
echo "完成！"

