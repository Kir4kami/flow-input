#!/bin/bash

#请小写
LLM="deepseek"
#1是完整通信树，4是任务切分并行
TASKNUM=4

# 切换到 TrafficGenerator 目录
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

# 根据 TASKNUM 执行不同的操作
if [ "$TASKNUM" -eq 1 ]; then
    # 单任务模式：执行合并操作并复制所有文件到 task1
    echo "Running in single-task mode (TASKNUM=4)"
    
    # 步骤2：执行 merge_dependency.sh
    echo "Running merge_dependency.sh..."
    bash merge_dependency.sh -i "${LLM}.txt" || { 
        echo "Error: merge_dependency.sh failed"; 
        exit 1; 
    }

    # 步骤3：执行 merge_rdma.sh
    echo "Running merge_rdma.sh..."
    bash merge_rdma.sh || { echo "Error: merge_rdma.sh failed"; exit 1; }

    echo "All merge scripts executed successfully!"

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

    # 移动依赖文件
    echo "Moving dependence.txt to task1 directory"
    if [ -f "dependence.txt" ]; then
        mv dependence.txt "$TARGET_DIR/"
    else
        echo "Error: dependence.txt not found in TrafficGenerator directory"
        exit 1
    fi
else
    # 多任务模式：分配特定目录到任务目录
    echo "Running in multi-task mode (TASKNUM=$TASKNUM)"
    
    # 定义要分配的目录列表
    declare -a task_dirs=(
        "1_TP1"
        "2_EP2"
        "3_PP3"
        "21_DP17"
    )

    # 检查任务数是否超过可用目录数
    if [ "$TASKNUM" -gt ${#task_dirs[@]} ]; then
        echo "Error: TASKNUM ($TASKNUM) exceeds available task directories (${#task_dirs[@]})"
        exit 1
    fi

    # 检查目录是否存在
    for dir in "${task_dirs[@]}"; do
        if [ ! -d "rdma_result/$dir" ]; then
            echo "Error: Required directory rdma_result/$dir not found!"
            exit 1
        fi
    done

    # 创建任务目录并复制内容
    for ((i=1; i<=TASKNUM; i++)); do
        TARGET_DIR="../task$i"
        SOURCE_DIR="rdma_result/${task_dirs[$((i-1))]}"
        
        # 删除旧目录（如果存在）
        if [ -d "$TARGET_DIR" ]; then
            echo "Removing existing $TARGET_DIR directory..."
            rm -rf "$TARGET_DIR" || { 
                echo "Error: Failed to remove old $TARGET_DIR directory"; 
                exit 1; 
            }
        fi

        # 创建新目录
        mkdir -p "$TARGET_DIR" || { 
            echo "Error: Failed to create $TARGET_DIR directory"; 
            exit 1; 
        }
        echo "Created directory: $TARGET_DIR"

        # 复制整个目录内容
        echo "Copying contents from $SOURCE_DIR to $TARGET_DIR..."
        cp -rv "$SOURCE_DIR"/* "$TARGET_DIR/" || {
            echo "Error: Failed to copy files from $SOURCE_DIR to $TARGET_DIR"
            exit 1
        }

        # 重命名 rdma_operate.txt 文件
        if [ -f "$TARGET_DIR/rdma_operate.txt" ]; then
            echo "Renaming rdma_operate.txt to rdma_operate0.txt in $TARGET_DIR"
            mv -v "$TARGET_DIR/rdma_operate.txt" "$TARGET_DIR/rdma_operate0.txt" || {
                echo "Error: Failed to rename file in $TARGET_DIR"
                exit 1
            }
        else
            echo "Warning: rdma_operate.txt not found in $TARGET_DIR"
        fi
    done
fi

# 返回上级目录并运行并行脚本
cd ..
echo "Running kira-parallel.sh with TASKNUM=$TASKNUM..."
bash kira-parallel.sh $TASKNUM