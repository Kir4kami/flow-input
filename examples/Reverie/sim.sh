#!/bin/bash

LLM="deepseek"

# 切换到 TrafficGenerator 目录（相对路径）
cd "$(dirname "$0")/TrafficGenerator" || exit 1

# 步骤1：执行 trafficGen.py
INPUT_FILE="${LLM}.txt"
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file $INPUT_FILE not found in $(pwd)!"
    exit 1
fi
echo "Running trafficGen.py with input: $INPUT_FILE..."
python3 trafficGen.py --input_file "$INPUT_FILE" || { 
    echo "Error: trafficGen.py failed"; 
    exit 1; 
}

# 步骤2：执行 merge_dependency.sh
echo "Running merge_dependency.sh..."
bash merge_dependency.sh -i "${LLM}.txt" || { 
    echo "Error: merge_dependency.sh failed"; 
    exit 1; 
}

# 步骤3：执行 merge_rdma.sh
echo "Running merge_rdma.sh..."
bash merge_rdma.sh || { echo "Error: merge_rdma.sh failed"; exit 1; }

echo "All scripts executed successfully!"

# 步骤4：复制生成的流量文件到 task1 目录
echo "Copying generated traffic files to task1 directory..."
TARGET_DIR="../task1"  # 相对于 TrafficGenerator 目录的路径

# 删除旧目录（如果存在）
if [ -d "$TARGET_DIR" ]; then
    echo "Removing existing task1 directory..."
    rm -rf "$TARGET_DIR" || { echo "Error: Failed to remove old task1 directory"; exit 1; }
fi

# 确保目标目录存在
mkdir -p "$TARGET_DIR" || { echo "Error: Failed to create task1 directory"; exit 1; }

# 复制所有流量文件
cp -v rdma_result/all_rdma_files/* "$TARGET_DIR/" || {
    echo "Error: Failed to copy traffic files to task1 directory"
    exit 1
}

echo "Successfully copied $(ls "$TARGET_DIR" | wc -l) files to task1 directory"

# 在sim.sh中的适当位置添加
echo "Moving dependence.txt to task1 directory"
if [ -f "dependence.txt" ]; then
    mv dependence.txt "$TARGET_DIR/"
    else
        echo "Error: dependence.txt not found in TrafficGenerator directory"
fi

cd ..
bash kira-parallel.sh