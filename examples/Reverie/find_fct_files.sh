#!/bin/bash

echo "=== 查找所有FCT相关文件 ==="
echo ""

cd /mnt/hgfs/flow-input-yf/examples/Reverie

echo "1. 在当前目录及子目录查找所有.fct文件:"
find . -name "*.fct*" -type f 2>/dev/null

echo ""
echo "2. 在dump目录查找所有文件:"
ls -lha dump/

echo ""
echo "3. 检查evaluation.fct是否存在（kira-parallel.sh中指定的路径）:"
if [ -f dump/evaluation.fct ]; then
    echo "[存在] dump/evaluation.fct 存在"
    ls -lh dump/evaluation.fct
    echo "内容:"
    head -50 dump/evaluation.fct
else
    echo "[不存在] dump/evaluation.fct 不存在"
fi

echo ""
echo "4. 检查build输出目录:"
ls -lh ../../build/examples/ 2>/dev/null | grep -E "fct|log|out" || echo "未找到相关文件"

echo ""
echo "5. 搜索包含'fct'的所有文件（最近1小时修改）:"
find . -type f -mmin -60 -name "*fct*" 2>/dev/null

echo ""
echo "6. 检查仿真是否真正运行:"
if [ -f dump/evaluation.out ]; then
    echo "evaluation.out大小: $(stat -c%s dump/evaluation.out) 字节"
    if [ -s dump/evaluation.out ]; then
        echo "内容:"
        cat dump/evaluation.out
    else
        echo "文件为空"
    fi
fi

echo ""
echo "7. 检查kira-parallel.sh中的输出路径配置:"
grep -n "FCTFILE\|DUMPFILE" kira-parallel.sh



