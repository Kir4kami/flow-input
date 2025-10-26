#!/bin/bash

# 拓扑切分按钮演示启动脚本
# 此脚本将启动 API 服务并打开演示页面

echo "=========================================="
echo "   拓扑切分按钮组件演示启动脚本"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3"
    echo "请先安装 Python 3.7 或更高版本"
    exit 1
fi

echo "✓ Python 已安装: $(python3 --version)"

# 检查依赖是否安装
echo ""
echo "检查依赖..."

check_dependency() {
    python3 -c "import $1" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "  ✓ $1 已安装"
        return 0
    else
        echo "  ✗ $1 未安装"
        return 1
    fi
}

MISSING_DEPS=0

for dep in fastapi uvicorn pydantic networkx requests; do
    if ! check_dependency "$dep"; then
        MISSING_DEPS=1
    fi
done

# 如果有缺失的依赖，提示安装
if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "⚠️  发现缺失的依赖"
    echo "正在安装依赖..."
    
    if [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt
    else
        pip3 install fastapi uvicorn pydantic networkx requests
    fi
    
    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败"
        echo "请手动运行: pip3 install fastapi uvicorn pydantic networkx requests"
        exit 1
    fi
    
    echo "✓ 依赖安装完成"
fi

echo ""
echo "=========================================="
echo "启动 API 服务..."
echo "=========================================="
echo ""

# 检查端口 8001 是否被占用
if lsof -Pi :8001 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  端口 8001 已被占用"
    echo "尝试关闭占用端口的进程..."
    
    PID=$(lsof -ti:8001)
    if [ ! -z "$PID" ]; then
        kill -9 $PID 2>/dev/null
        sleep 1
        echo "✓ 已关闭旧进程"
    fi
fi

# 在后台启动 API 服务
echo "正在启动 API 服务 (http://localhost:8001)..."
python3 start_tree_cut_api.py > /tmp/tree_cut_api.log 2>&1 &
API_PID=$!

# 保存 PID 到文件
echo $API_PID > /tmp/tree_cut_api.pid

# 等待服务启动
echo "等待服务启动..."
sleep 3

# 检查服务是否成功启动
if ps -p $API_PID > /dev/null 2>&1; then
    echo "✓ API 服务已启动 (PID: $API_PID)"
    
    # 测试 API 健康检查
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "✓ API 服务健康检查通过"
    else
        echo "⚠️  API 服务可能未完全启动，稍后重试"
    fi
else
    echo "❌ API 服务启动失败"
    echo "查看日志: cat /tmp/tree_cut_api.log"
    exit 1
fi

echo ""
echo "=========================================="
echo "打开演示页面..."
echo "=========================================="
echo ""

# 检查并打开浏览器
DEMO_FILE="$SCRIPT_DIR/demo.html"

if [ ! -f "$DEMO_FILE" ]; then
    echo "❌ 错误: 未找到演示文件 demo.html"
    exit 1
fi

echo "演示文件: $DEMO_FILE"

# 尝试使用不同的浏览器打开
if command -v xdg-open &> /dev/null; then
    xdg-open "$DEMO_FILE" &
    echo "✓ 已使用默认浏览器打开演示页面"
elif command -v firefox &> /dev/null; then
    firefox "$DEMO_FILE" &
    echo "✓ 已使用 Firefox 打开演示页面"
elif command -v google-chrome &> /dev/null; then
    google-chrome "$DEMO_FILE" &
    echo "✓ 已使用 Chrome 打开演示页面"
elif command -v chromium-browser &> /dev/null; then
    chromium-browser "$DEMO_FILE" &
    echo "✓ 已使用 Chromium 打开演示页面"
else
    echo "⚠️  无法自动打开浏览器"
    echo "请手动在浏览器中打开: $DEMO_FILE"
fi

echo ""
echo "=========================================="
echo "✓ 演示启动完成！"
echo "=========================================="
echo ""
echo "📌 API 服务地址: http://localhost:8001"
echo "📌 API 文档地址: http://localhost:8001/docs"
echo "📌 演示页面: $DEMO_FILE"
echo ""
echo "📝 提示:"
echo "  - 点击页面上的'拓扑切分'按钮即可测试"
echo "  - API 日志: tail -f /tmp/tree_cut_api.log"
echo "  - 停止服务: ./stop_demo.sh 或 kill $API_PID"
echo ""
echo "按 Ctrl+C 退出 (API 服务将继续在后台运行)"
echo ""

# 创建停止脚本
cat > "$SCRIPT_DIR/stop_demo.sh" << 'EOF'
#!/bin/bash

echo "正在停止 API 服务..."

if [ -f /tmp/tree_cut_api.pid ]; then
    PID=$(cat /tmp/tree_cut_api.pid)
    
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo "✓ API 服务已停止 (PID: $PID)"
        rm /tmp/tree_cut_api.pid
    else
        echo "⚠️  进程不存在"
        rm /tmp/tree_cut_api.pid
    fi
else
    echo "⚠️  未找到 PID 文件"
    
    # 尝试通过端口查找并关闭
    PID=$(lsof -ti:8001)
    if [ ! -z "$PID" ]; then
        kill $PID
        echo "✓ 已关闭端口 8001 的进程 (PID: $PID)"
    else
        echo "未找到占用端口 8001 的进程"
    fi
fi

echo "完成"
EOF

chmod +x "$SCRIPT_DIR/stop_demo.sh"

# 等待用户输入或保持运行
read -p "按回车键继续查看 API 日志 (或按 Ctrl+C 退出): " -r

# 显示实时日志
if [ -f /tmp/tree_cut_api.log ]; then
    echo ""
    echo "=========================================="
    echo "API 服务实时日志"
    echo "=========================================="
    echo ""
    tail -f /tmp/tree_cut_api.log
fi



