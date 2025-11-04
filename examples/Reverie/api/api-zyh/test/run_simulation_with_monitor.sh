#!/bin/bash

echo "  仿真 + 稳态监控 自动同步启动脚本"
echo ""

# 配置参数
API_HOST="0.0.0.0"
API_PORT="8001"
POLL_STRATEGY="medium"  # high/medium/low
MIXED_GRANULARITY="true"

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$(dirname "$SCRIPT_DIR")"  # API目录是test的上级目录
REVERIE_DIR="$(dirname "$API_DIR")"  # Reverie目录是API的上级目录

echo "工作目录: $REVERIE_DIR"
echo "API目录: $API_DIR"
echo ""

# ==================== 步骤1: 启动稳态监控API ====================
echo "步骤1: 启动稳态监控API..."

# 检查端口是否被占用
if lsof -Pi :$API_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "警告: 端口 $API_PORT 已被占用，正在关闭..."
    PID=$(lsof -ti:$API_PORT)
    kill -9 $PID 2>/dev/null
    sleep 1
fi

# 在后台启动API服务器
cd "$API_DIR"
nohup python3 steady_state_monitor_api.py > "$SCRIPT_DIR/api.log" 2>&1 &
API_PID=$!
echo "[成功] API已启动 (PID: $API_PID)"
echo "   访问地址: http://$API_HOST:$API_PORT"
echo "   日志文件: $SCRIPT_DIR/api.log"

# 等待API启动
echo "   等待API服务启动..."
sleep 3

# 验证API是否正常运行
if curl -s http://localhost:$API_PORT/ > /dev/null 2>&1; then
    echo "[成功] API服务正常运行"
else
    echo "[失败] API服务启动失败，请检查 $SCRIPT_DIR/api.log"
    exit 1
fi

echo ""

# ==================== 步骤2: 自动启动稳态监控 ====================
echo "步骤2: 启动稳态监控任务..."

# 调用API启动监控
MONITOR_RESPONSE=$(curl -s -X POST "http://localhost:$API_PORT/start-monitor" \
    -H "Content-Type: application/json" \
    -d "{
        \"mixed_granularity_enabled\": $MIXED_GRANULARITY,
        \"poll_strategy\": \"$POLL_STRATEGY\"
    }")

echo "监控启动响应: $MONITOR_RESPONSE"

if echo "$MONITOR_RESPONSE" | grep -q '"success":true'; then
    echo "[成功] 稳态监控已启动"
    POLL_INTERVAL=$(echo "$MONITOR_RESPONSE" | grep -o '"poll_interval_microseconds":[0-9.]*' | cut -d: -f2)
    echo "   轮询间隔: ${POLL_INTERVAL} 微秒"
else
    echo "[失败] 监控启动失败"
fi

echo ""

# ==================== 步骤3: 启动仿真 ====================
echo "步骤3: 启动仿真..."

cd "$REVERIE_DIR"

# 清空旧的日志文件
echo "清空旧日志..."
rm -f dump/evaluation.out dump/evaluation.fct* flow_stats.txt

# 在后台运行仿真
echo "启动仿真（后台运行）..."
bash sim.sh > sim_output.log 2>&1 &
SIM_PID=$!
echo "[成功] 仿真已启动 (PID: $SIM_PID)"
echo "   输出日志: $REVERIE_DIR/sim_output.log"

echo ""

# ==================== 步骤4: 实时监控稳态状态 ====================
echo "步骤4: 实时监控稳态状态..."
echo "按 Ctrl+C 停止监控"
echo ""

CHECK_COUNT=0
MAX_CHECKS=10000  # 最多检查10000次
CHECK_INTERVAL=0.1  # 每0.1秒检查一次

while [ $CHECK_COUNT -lt $MAX_CHECKS ]; do
    # 检查仿真是否还在运行
    if ! kill -0 $SIM_PID 2>/dev/null; then
        echo ""
        echo "仿真已完成！"
        break
    fi
    
    # 查询稳态状态
    STATUS=$(curl -s http://localhost:$API_PORT/steady-state-status)
    
    # 解析状态
    IS_MONITORING=$(echo "$STATUS" | grep -o '"is_monitoring":[^,]*' | cut -d: -f2)
    IS_STEADY=$(echo "$STATUS" | grep -o '"is_in_steady_state":[^,]*' | cut -d: -f2)
    STEADY_COUNT=$(echo "$STATUS" | grep -o '"steady_state_count":[0-9]*' | cut -d: -f2)
    
    # 显示当前状态
    printf "\r[检查 %d] 监控中: %s | 稳态: %s | 稳态次数: %s" \
        $CHECK_COUNT "$IS_MONITORING" "$IS_STEADY" "$STEADY_COUNT"
    
    # 如果进入稳态，显示提示
    if [ "$IS_STEADY" = "true" ]; then
        echo ""
        echo "       检测到进入稳态！"
        echo "稳态次数: $STEADY_COUNT"
        echo ""
        echo "完整状态:"
        echo "$STATUS" | python3 -m json.tool 2>/dev/null || echo "$STATUS"
        echo ""
    fi
    
    CHECK_COUNT=$((CHECK_COUNT + 1))
    sleep $CHECK_INTERVAL
done

echo ""
echo ""

# ==================== 步骤5: 等待仿真完成 ====================
if kill -0 $SIM_PID 2>/dev/null; then
    echo "步骤5: 等待仿真完成..."
    wait $SIM_PID
    echo "[成功] 仿真已完成"
fi

echo ""

# ==================== 步骤6: 停止监控并查看结果 ====================
echo "步骤6: 停止监控并查看结果..."

# 停止监控
STOP_RESPONSE=$(curl -s -X POST "http://localhost:$API_PORT/stop-monitor" \
    -H "Content-Type: application/json" \
    -d '{"save_history": true}')

echo "监控停止响应:"
echo "$STOP_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STOP_RESPONSE"

echo ""

# 查看稳态历史
echo "稳态历史记录:"
HISTORY=$(curl -s http://localhost:$API_PORT/steady-state-history)
echo "$HISTORY" | python3 -m json.tool 2>/dev/null || echo "$HISTORY"

echo ""

# ==================== 步骤7: 显示结果摘要 ====================
echo "  完成！结果摘要"
echo ""

echo "仿真结果文件:"
ls -lh dump/*.fct* dump/*.out 2>/dev/null || echo "未找到结果文件"

echo ""
echo "稳态监控日志:"
if [ -f dump/steady_state_history.json ]; then
    echo "  稳态历史: dump/steady_state_history.json"
    cat dump/steady_state_history.json
else
    echo "  未生成稳态历史文件"
fi

echo ""
echo "API服务仍在运行，可以继续查询："
echo "  查看状态: curl http://localhost:$API_PORT/steady-state-status"
echo "  查看历史: curl http://localhost:$API_PORT/steady-state-history"
echo "  停止API: kill $API_PID"
echo ""
echo "API PID: $API_PID 已保存到 $SCRIPT_DIR/api_pid.txt"
echo $API_PID > "$SCRIPT_DIR/api_pid.txt"



