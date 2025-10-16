#!/bin/bash

# Flow-Input Docker 清理脚本

echo "🧹 清理 Flow-Input Docker 环境..."

# 停止并删除容器
docker-compose down

# 删除镜像
echo "🗑️ 删除 Docker 镜像..."
docker rmi flow-input_flow-input 2>/dev/null || true
docker rmi flow-input_jupyter 2>/dev/null || true

# 清理未使用的资源
echo "🧽 清理未使用的 Docker 资源..."
docker system prune -f

echo "✅ 清理完成！"
