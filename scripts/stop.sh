#!/bin/bash

# Flow-Input Docker 停止脚本

echo "🛑 停止 Flow-Input Docker 服务..."

# 停止所有服务
docker-compose down

echo "✅ 所有服务已停止！"
