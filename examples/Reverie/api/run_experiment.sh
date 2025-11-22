#!/bin/bash
# 一键运行实验
# 使用方法：在VM中运行 bash run_experiment.sh

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              四配置对比实验 - 一键启动                          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 切换到工作目录
cd /home/chanel/flow-input-local/examples/Reverie/api

# 步骤1: 清理旧端口
echo "[步骤 1/3] 清理端口 8000..."
sudo lsof -ti:8000 | xargs sudo kill -9 2>/dev/null && echo "✓ 端口已清理" || echo "✓ 端口未占用"
sleep 1

# 步骤2: 启动API
echo ""
echo "[步骤 2/3] 启动 API 服务..."
python3 complete_api.py > api.log 2>&1 &
API_PID=$!
echo "✓ API 已启动 (PID: $API_PID)"
echo "  日志文件: $(pwd)/api.log"

# 等待API启动
echo ""
echo "等待 API 初始化..."
for i in {1..10}; do
    sleep 1
    if curl -s http://localhost:8000/ > /dev/null 2>&1; then
        echo "✓ API 就绪!"
        break
    fi
    echo -n "."
done

# 步骤3: 运行实验
echo ""
echo "[步骤 3/3] 运行四配置对比实验"
echo ""

# 检查脚本是否存在
if [ ! -f "quick_comparison.py" ]; then
    echo "❌ 脚本不存在: quick_comparison.py"
    echo ""
    echo "请先运行同步脚本:"
    echo "  bash sync_experiment_files.sh"
    exit 1
fi

# 运行实验
python3 quick_comparison.py

# 结束
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "实验完成！"
echo ""
echo "查看结果:"
echo "  - 终端输出（已显示）"
echo "  - JSON文件: ../experiment_results/"
echo "  - API日志: $(pwd)/api.log"
echo ""
echo "停止API服务:"
echo "  kill $API_PID"
echo "════════════════════════════════════════════════════════════════"





















