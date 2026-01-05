#!/bin/bash
# 从生成的负载中提取所有主机节点之间的流
# 在Linux上直接运行

cd "$(dirname "$0")"

echo "============================================================"
echo "从生成的负载中提取所有主机节点之间的流"
echo "============================================================"
echo ""

# 检查Python脚本是否存在
if [ ! -f "extract_all_host_flows.py" ]; then
    echo "错误: extract_all_host_flows.py 不存在"
    exit 1
fi

# 运行Python脚本
python3 extract_all_host_flows.py "$@"


