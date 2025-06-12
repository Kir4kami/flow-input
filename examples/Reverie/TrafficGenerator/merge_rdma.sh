#!/bin/bash

cd rdma_result || exit

# 创建目标目录
mkdir -p all_rdma_files
count=0

while IFS= read -r dir; do
    pushd "$dir" > /dev/null
    # 精确匹配文件：仅 rdma_operate[0-9]*.txt 和 rdma_operate.txt
    for file in $(find . -maxdepth 1 -name 'rdma_operate*.txt' | sort -V); do
        cp -- "$file" "../all_rdma_files/rdma_operate$((count++)).txt"
    done
    popd > /dev/null
done < <(find . -maxdepth 1 -type d -regex './[0-9]+_[A-Z]+[0-9]*' | sort -t_ -k1n)

echo "实际合并文件数: $count"