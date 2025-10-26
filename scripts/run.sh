#!/bin/bash

# Flow-Input Docker 运行脚本

set -e

echo "🐳 启动 Flow-Input Docker 容器..."

# 检查容器是否已存在
if docker ps -a --format "table {{.Names}}" | grep -q "flow-input-container"; then
    echo "🔄 停止现有容器..."
    docker-compose down
fi

# 启动容器
echo "🚀 启动新容器..."
docker-compose up -d

echo "✅ 容器已启动！"
echo ""
echo "进入容器："
echo "docker exec -it flow-input-container bash"
echo ""
echo "查看日志："
echo "docker-compose logs -f"
echo ""
echo "停止容器："
echo "./scripts/stop.sh"
