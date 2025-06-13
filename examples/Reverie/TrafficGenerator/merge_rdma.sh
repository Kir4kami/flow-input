#!/bin/bash

cd rdma_result || exit

# 创建目标目录
mkdir -p all_rdma_files
count=0

# 修复方案：使用更健壮的目录排序方式
while IFS= read -r dir; do
    pushd "$dir" > /dev/null
    for file in $(find . -maxdepth 1 -name 'rdma_operate*.txt' | sort -V); do
        cp -- "$file" "../all_rdma_files/rdma_operate$((count++)).txt"
    done
    popd > /dev/null
# 关键修改：使用自然排序处理带数字的目录名
done < <(find . -maxdepth 1 -type d -regex './[0-9]+_[A-Z]+[0-9]*' | 
         sed 's/^\.\///' |   # 移除 ./ 前缀
         sort -V |           # 使用自然排序
         sed 's/^/.\//')     # 添加回 ./ 前缀

echo "实际合并文件数: $count"