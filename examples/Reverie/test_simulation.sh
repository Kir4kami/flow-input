#!/bin/bash

# 发送仿真请求（后台）
echo "=== 开始仿真 ==="
curl -X POST "http://localhost:8000/run-simulation" \
  -H "Content-Type: application/json" \
  -d '{"task_num": 1, "llm_model": "deepseek", "enable_mixed_granularity": false, "simulation_time": 600.0}' &

# 立即开始循环查询
for i in {1..10}; do
    sleep 1
    echo ""
    echo "=== 第 $i 秒查询 ==="
    curl -s -X GET "http://localhost:8000/simulation-status" | python3 -m json.tool
done
