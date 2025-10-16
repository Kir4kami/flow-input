#!/bin/bash

# Flow-Input Jupyter 服务启动脚本

set -e

echo "📓 启动 Flow-Input Jupyter 服务..."

# 启动 Jupyter 服务
docker-compose --profile jupyter up -d jupyter

echo "✅ Jupyter 服务已启动！"
echo ""
echo "访问地址："
echo "http://localhost:8888"
echo ""
echo "停止服务："
echo "./scripts/stop.sh"
