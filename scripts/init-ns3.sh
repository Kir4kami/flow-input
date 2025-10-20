#!/bin/bash

# NS-3 初始化脚本

echo "🔧 初始化 NS-3 环境..."

# 检查是否已经构建过
if [ -f "/workspace/build/ns3" ]; then
    echo "✅ NS-3 已经构建完成"
    exit 0
fi

echo "📦 开始构建 NS-3..."
cd /workspace

# 配置 NS-3
echo "⚙️ 配置 NS-3..."
./ns3 configure --enable-examples --enable-tests

# 构建 NS-3
echo "🔨 构建 NS-3..."
./ns3 build

echo "✅ NS-3 构建完成！"
