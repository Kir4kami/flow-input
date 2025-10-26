#!/bin/bash

# Flow-Input Docker 构建脚本

set -e

echo "🚀 开始构建 Flow-Input Docker 环境..."

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

# 检查 docker-compose 是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose 未安装，请先安装 docker-compose"
    exit 1
fi

# 创建必要的目录
mkdir -p results data

# 构建镜像
echo "📦 构建 Docker 镜像..."
docker-compose build

echo "✅ 构建完成！"
echo ""
echo "使用方法："
echo "1. 启动容器：./scripts/run.sh"
echo "2. 启动 Jupyter：./scripts/run-jupyter.sh"
echo "3. 停止容器：./scripts/stop.sh"
