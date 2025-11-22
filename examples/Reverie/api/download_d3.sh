#!/bin/bash
# D3.js 下载脚本

echo "====================================="
echo "  D3.js 本地下载脚本"
echo "====================================="

cd "$(dirname "$0")"

# 尝试使用wget下载
if command -v wget &> /dev/null; then
    echo "使用wget下载 D3.js v7..."
    wget https://d3js.org/d3.v7.min.js -O d3.v7.min.js
    
    if [ $? -eq 0 ]; then
        echo "✅ D3.js 下载成功！"
        echo "文件位置: $(pwd)/d3.v7.min.js"
        exit 0
    else
        echo "❌ wget下载失败"
    fi
fi

# 尝试使用curl下载
if command -v curl &> /dev/null; then
    echo "使用curl下载 D3.js v7..."
    curl -o d3.v7.min.js https://d3js.org/d3.v7.min.js
    
    if [ $? -eq 0 ]; then
        echo "✅ D3.js 下载成功！"
        echo "文件位置: $(pwd)/d3.v7.min.js"
        exit 0
    else
        echo "❌ curl下载失败"
    fi
fi

echo ""
echo "❌ 自动下载失败，请手动下载："
echo ""
echo "方法1（Windows上）："
echo "  1. 在Windows浏览器访问: https://d3js.org/d3.v7.min.js"
echo "  2. 右键另存为: d3.v7.min.js"
echo "  3. 将文件复制到虚拟机共享文件夹："
echo "     C:\\Users\\杨帆\\Desktop\\导师\\flow-input-yf\\examples\\Reverie\\api\\"
echo ""
echo "方法2（使用Python）："
echo "  python3 -c 'import urllib.request; urllib.request.urlretrieve(\"https://d3js.org/d3.v7.min.js\", \"d3.v7.min.js\")'"
echo ""

exit 1

